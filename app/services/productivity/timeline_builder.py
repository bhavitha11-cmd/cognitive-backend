from datetime import date, datetime, timezone, timedelta, time
from typing import Any, Optional
import uuid
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.employee_break import EmployeeBreak
from app.models.task_work_session import TaskWorkSession
from app.models.idle_classification import IdleClassification
from app.models.idle_reason_master import IdleReasonMaster
from app.services.productivity.kpi_calculator import IST, get_day_boundaries_utc

_EVENT_PRIORITY = {
    "CLOCK_IN": 0,
    "TASK_START": 1,
    "TASK_RESUME": 2,
    "BREAK_START": 3,
    "BREAK_END": 4,
    "IDLE": 5,
    "TASK_END": 6,
    "CLOCK_OUT": 7
}


def to_ist(dt: datetime) -> datetime:
    """Convert a datetime (potentially UTC) to IST timezone."""
    if not dt:
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


class TimelineBuilder:
    @staticmethod
    def _format_time_id(dt: datetime) -> str:
        """Helper to format datetime for segment identifiers (e.g. 1515)."""
        return dt.strftime("%H%M")

    @classmethod
    def build_daily_timeline(
        cls,
        db: Session,
        employee_id: uuid.UUID,
        query_date: date,
        now_utc: datetime
    ) -> list[dict[str, Any]]:
        """Reconstruct the daily timeline chronologically, showing all events and dynamic idle segments."""
        # 1. Fetch Attendance
        attendance = db.scalar(
            select(Attendance).where(
                Attendance.employee_id == employee_id,
                Attendance.date == query_date,
            )
        )
        if not attendance or not attendance.clock_in:
            return []

        clock_in = attendance.clock_in
        clock_out = attendance.clock_out
        timeline_end = clock_out or now_utc

        timeline: list[dict[str, Any]] = []

        # Add Clock-In Event
        timeline.append({
            "time": to_ist(clock_in).isoformat(),
            "event_type": "CLOCK_IN",
            "title": "Clocked In",
            "description": "Entered work center",
            "metadata": {"notes": attendance.notes}
        })

        if clock_out:
            # Add Clock-Out Event
            timeline.append({
                "time": to_ist(clock_out).isoformat(),
                "event_type": "CLOCK_OUT",
                "title": "Clocked Out",
                "description": "Exited work center",
                "metadata": {}
            })

        # 2. Fetch Breaks
        breaks = db.scalars(
            select(EmployeeBreak).where(
                EmployeeBreak.employee_id == employee_id,
                EmployeeBreak.date == query_date,
            )
        ).all()

        active_intervals = []

        for b in breaks:
            b_start = b.break_start
            b_end = b.break_end or now_utc
            active_intervals.append((b_start, b_end, "BREAK", b))

            timeline.append({
                "time": to_ist(b_start).isoformat(),
                "event_type": "BREAK_START",
                "title": "Break Started",
                "description": b.remarks or "Took a break",
                "metadata": {"break_id": str(b.id)}
            })
            if b.break_end:
                timeline.append({
                    "time": to_ist(b.break_end).isoformat(),
                    "event_type": "BREAK_END",
                    "title": "Resume",
                    "description": "Resumed from break",
                    "metadata": {"break_id": str(b.id)}
                })

        # 3. Fetch Task Work Sessions using IST day boundaries converted to UTC
        day_start, day_end = get_day_boundaries_utc(query_date)
        sessions = db.scalars(
            select(TaskWorkSession).where(
                TaskWorkSession.employee_id == employee_id,
                TaskWorkSession.start_time >= day_start,
                TaskWorkSession.start_time <= day_end,
            )
        ).all()

        for s in sessions:
            s_start = s.start_time
            s_end = s.end_time or now_utc
            active_intervals.append((s_start, s_end, "TASK", s))

            task_code = s.task.task_code if s.task else "TSK"
            task_title = s.task.title if s.task else "Unknown Task"
            project_name = s.project.name if s.project else "Unknown Project"

            timeline.append({
                "time": to_ist(s_start).isoformat(),
                "event_type": "TASK_START",
                "title": "Task Started" if s.session_type == "REGULAR" else "Rework Started",
                "description": f"Started working on [{task_code}] {task_title}",
                "metadata": {
                    "session_id": str(s.id),
                    "task_id": str(s.task_id),
                    "task_code": task_code,
                    "task_title": task_title,
                    "project_name": project_name,
                    "session_type": s.session_type
                }
            })

            if s.end_time:
                timeline.append({
                    "time": to_ist(s.end_time).isoformat(),
                    "event_type": "TASK_END",
                    "title": "Task Session Ended" if s.status == "COMPLETED" else "Task Paused",
                    "description": s.remarks or f"Finished session for [{task_code}]",
                    "metadata": {
                        "session_id": str(s.id),
                        "status": s.status
                    }
                })

        # 4. Compute Gaps (Idle Gaps)
        # Sort active intervals chronologically
        active_intervals.sort(key=lambda x: x[0])

        # Resolve saved classifications for this day
        classifications = db.scalars(
            select(IdleClassification).where(
                IdleClassification.employee_id == employee_id,
                IdleClassification.date == query_date,
            )
        ).all()
        class_map = {c.idle_segment_identifier: c for c in classifications}

        # Find gaps
        current_time = clock_in
        for start, end, itype, _ in active_intervals:
            if start > current_time:
                gap_duration = (start - current_time).total_seconds()
                if gap_duration >= 60:  # Gap of at least 1 minute
                    cls._create_idle_timeline_item(current_time, start, class_map, timeline)
            current_time = max(current_time, end)

        if current_time < timeline_end:
            gap_duration = (timeline_end - current_time).total_seconds()
            if gap_duration >= 60:
                cls._create_idle_timeline_item(current_time, timeline_end, class_map, timeline)

        # Sort timeline chronologically and deterministically by priority
        timeline.sort(key=lambda x: (x["time"], _EVENT_PRIORITY.get(x["event_type"], 99)))
        return timeline

    @classmethod
    def _create_idle_timeline_item(
        cls,
        start: datetime,
        end: datetime,
        class_map: dict[str, IdleClassification],
        timeline: list[dict[str, Any]]
    ):
        """Create and append an idle gap item to the timeline list."""
        # Convert start/end to IST for display
        ist_start = to_ist(start)
        ist_end = to_ist(end)
        segment_id = f"idle_{cls._format_time_id(start)}_{cls._format_time_id(end)}"
        duration_minutes = int((end - start).total_seconds() // 60)

        classification = class_map.get(segment_id)
        reason_name = "Unclassified"
        reason_color = "#9CA3AF"
        remarks = None
        is_classified = False

        if classification:
            is_classified = True
            reason_name = classification.reason.name if classification.reason else "Other"
            reason_color = classification.reason.color if classification.reason else "#9CA3AF"
            remarks = classification.remarks

        timeline.append({
            "time": ist_start.isoformat(),
            "event_type": "IDLE",
            "title": "Idle" if not is_classified else f"Idle ({reason_name})",
            "description": f"Unallocated time gap for {duration_minutes} minutes",
            "metadata": {
                "idle_segment_identifier": segment_id,
                "duration_minutes": duration_minutes,
                "start_time": ist_start.isoformat(),
                "end_time": ist_end.isoformat(),
                "is_classified": is_classified,
                "reason_name": reason_name,
                "reason_color": reason_color,
                "remarks": remarks
            }
        })

