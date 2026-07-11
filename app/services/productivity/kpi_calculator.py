import os
from datetime import date, datetime, timezone, timedelta, time
from typing import Any, Optional
import uuid
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.employee_break import EmployeeBreak
from app.models.task_work_session import TaskWorkSession
from app.models.attendance_rule import AttendanceRule
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.task_continuity import TaskPauseHistory

# Configurable local timezone — read from environment, default to Asia/Kolkata
_LOCAL_TZ_NAME = os.environ.get("LOCAL_TIMEZONE", "Asia/Kolkata")
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo(_LOCAL_TZ_NAME)
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=5, minutes=30))  # fallback IST

# Keep IST as an alias for backward compatibility
IST = LOCAL_TZ


def get_day_boundaries_utc(query_date: date) -> tuple[datetime, datetime]:
    """Convert a local query date in the configured local timezone to UTC start and end boundaries."""
    local_start = datetime.combine(query_date, time.min).replace(tzinfo=LOCAL_TZ)
    local_end = datetime.combine(query_date, time.max).replace(tzinfo=LOCAL_TZ)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


class KPICalculator:
    @staticmethod
    def format_seconds(seconds: int) -> str:
        """Format total seconds into HH:MM:SS format."""
        negative = seconds < 0
        abs_seconds = abs(seconds)
        hrs = abs_seconds // 3600
        mins = (abs_seconds % 3600) // 60
        secs = abs_seconds % 60
        sign = "-" if negative else ""
        return f"{sign}{hrs:02d}:{mins:02d}:{secs:02d}"

    @classmethod
    def make_kpi_object(
        cls,
        name: str,
        raw_seconds: int,
        expected_seconds: float | None = None,
        percentage_override: float | None = None,
        formula: str = "",
        rule: Optional[AttendanceRule] = None
    ) -> dict[str, Any]:
        """Generate a standard KPI dictionary object."""
        hours = round(raw_seconds / 3600.0, 2)
        minutes = round(raw_seconds / 60.0, 2)
        formatted = cls.format_seconds(raw_seconds)

        pct = 0.0
        if percentage_override is not None:
            pct = round(percentage_override, 2)
        elif expected_seconds and expected_seconds > 0:
            pct = round((raw_seconds / expected_seconds) * 100, 2)

        color = "#6B7280"  # default gray
        status = "default"
        tooltip = f"{hours} hrs"

        if name == "Presence Time":
            tooltip = f"Total physical presence time (Clock Out - Clock In): {formatted}"
            color = "#3B82F6"  # Blue
            status = "info"
        elif name == "Break Time":
            tooltip = f"Total break time taken: {formatted}"
            max_break = (rule.max_break_minutes * 60) if rule else 3600
            if raw_seconds > max_break:
                status = "danger"
                color = "#EF4444"  # Red
                tooltip += f" (Exceeded limit of {rule.max_break_minutes} mins)"
            else:
                status = "warning"
                color = "#F59E0B"  # Yellow/Orange
        elif name == "Organization Time":
            tooltip = f"Total organization time (Presence - Break): {formatted}"
            color = "#10B981"  # Green
            status = "success"
        elif name == "Productive Time":
            tooltip = f"Total task work session time: {formatted}"
            req_sec = (float(rule.required_productive_hours) * 3600) if rule else 28800
            if raw_seconds >= req_sec:
                status = "success"
                color = "#10B981"
            elif raw_seconds >= req_sec * 0.75:
                status = "warning"
                color = "#F59E0B"
            else:
                status = "danger"
                color = "#EF4444"
        elif name == "Idle Time":
            tooltip = f"Total unallocated time: {formatted}"
            if raw_seconds > 7200:  # > 2 hrs
                status = "danger"
                color = "#EF4444"
            elif raw_seconds > 3600:  # > 1 hr
                status = "warning"
                color = "#F59E0B"
            else:
                status = "success"
                color = "#10B981"
        elif name == "Remaining Productive Time":
            tooltip = f"Time remaining to target: {formatted}"
            if raw_seconds == 0:
                status = "success"
                color = "#10B981"
                tooltip = "Productivity target achieved!"
            else:
                status = "warning"
                color = "#F59E0B"
        elif name == "Productivity %":
            tooltip = f"Productivity Ratio (Productive / Org * 100): {pct}%"
            if pct >= 80:
                status = "success"
                color = "#10B981"
            elif pct >= 60:
                status = "warning"
                color = "#F59E0B"
            else:
                status = "danger"
                color = "#EF4444"
            formatted = f"{pct:.1f}%"
        elif name == "Organization Utilization %":
            tooltip = f"Organization Utilization (Org / Presence * 100): {pct}%"
            if pct >= 80:
                status = "success"
                color = "#10B981"
            else:
                status = "warning"
                color = "#F59E0B"
            formatted = f"{pct:.1f}%"
        elif name == "Attendance Utilization %":
            tooltip = f"Attendance Utilization (Productive / Presence * 100): {pct}%"
            if pct >= 75:
                status = "success"
                color = "#10B981"
            else:
                status = "warning"
                color = "#F59E0B"
            formatted = f"{pct:.1f}%"
        elif name == "Break %":
            tooltip = f"Break Ratio (Break / Presence * 100): {pct}%"
            formatted = f"{pct:.1f}%"
        elif name == "Idle %":
            tooltip = f"Idle Ratio (Idle / Presence * 100): {pct}%"
            formatted = f"{pct:.1f}%"

        return {
            "raw_seconds": raw_seconds,
            "hours": hours,
            "minutes": minutes,
            "formatted": formatted,
            "percentage": pct,
            "status": status,
            "color": color,
            "tooltip": tooltip,
            "formula": formula,
        }

    @staticmethod
    def merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
        """Merge overlapping time intervals."""
        if not intervals:
            return []
        sorted_intervals = sorted(intervals, key=lambda x: x[0])
        merged = [sorted_intervals[0]]
        for current in sorted_intervals[1:]:
            prev_start, prev_end = merged[-1]
            curr_start, curr_end = current
            if curr_start <= prev_end:
                merged[-1] = (prev_start, max(prev_end, curr_end))
            else:
                merged.append(current)
        return merged

    @classmethod
    def subtract_intervals(
        cls,
        task_intervals: list[tuple[datetime, datetime]],
        break_intervals: list[tuple[datetime, datetime]]
    ) -> list[tuple[datetime, datetime]]:
        """Subtract a list of break intervals from task intervals."""
        merged_breaks = cls.merge_intervals(break_intervals)
        result = []
        for t_start, t_end in task_intervals:
            curr_intervals = [(t_start, t_end)]
            for b_start, b_end in merged_breaks:
                next_intervals = []
                for s_start, s_end in curr_intervals:
                    if b_end <= s_start or b_start >= s_end:
                        next_intervals.append((s_start, s_end))
                    else:
                        if b_start > s_start:
                            next_intervals.append((s_start, b_start))
                        if b_end < s_end:
                            next_intervals.append((b_end, s_end))
                curr_intervals = next_intervals
            result.extend(curr_intervals)
        return result

    @classmethod
    def process_intervals(
        cls,
        clock_in: datetime,
        clock_out: datetime,
        task_sessions: list[tuple[datetime, datetime]],
        break_sessions: list[tuple[datetime, datetime]]
    ) -> int:
        """
        Calculates productive seconds using explicit order of operations:
        1. Clamp task and break sessions to presence window (clock_in -> clock_out)
        2. Merge overlapping task intervals
        3. Merge overlapping break intervals
        4. Subtract merged break intervals from merged task intervals
        5. Sum remaining task durations to calculate final productive seconds
        """
        # 1. Clamp to presence window
        clamped_tasks = []
        for start, end in task_sessions:
            start_clamp = max(start, clock_in)
            end_clamp = min(end, clock_out)
            if start_clamp < end_clamp:
                clamped_tasks.append((start_clamp, end_clamp))

        clamped_breaks = []
        for start, end in break_sessions:
            start_clamp = max(start, clock_in)
            end_clamp = min(end, clock_out)
            if start_clamp < end_clamp:
                clamped_breaks.append((start_clamp, end_clamp))

        # 2. Merge task intervals
        merged_tasks = cls.merge_intervals(clamped_tasks)

        # 3. Merge break intervals
        merged_breaks = cls.merge_intervals(clamped_breaks)

        # 4. Subtract breaks from tasks
        final_intervals = cls.subtract_intervals(merged_tasks, merged_breaks)

        # 5. Sum durations
        productive_seconds = sum(int((end - start).total_seconds()) for start, end in final_intervals)
        return max(0, productive_seconds)

    @classmethod
    def calculate_raw_metrics(
        cls,
        db: Session,
        employee_id: uuid.UUID,
        query_date: date,
        now_utc: datetime
    ) -> dict[str, int]:
        """Compute presence, break, and productive seconds from raw DB tables."""
        # 1. Fetch Attendance record
        attendance = db.scalar(
            select(Attendance).where(
                Attendance.employee_id == employee_id,
                Attendance.date == query_date,
            )
        )
        presence_seconds = 0
        if attendance and attendance.clock_in:
            cin = attendance.clock_in
            cout = attendance.clock_out
            if cout:
                presence_seconds = int((cout - cin).total_seconds())
            else:
                presence_seconds = int((now_utc - cin).total_seconds())
        presence_seconds = max(0, presence_seconds)

        if not attendance or not attendance.clock_in:
            return {
                "presence_seconds": 0,
                "break_seconds": 0,
                "productive_seconds": 0,
            }

        cin = attendance.clock_in
        cout = attendance.clock_out or now_utc

        # 2. Fetch Break records for query date
        breaks = db.scalars(
            select(EmployeeBreak).where(
                EmployeeBreak.employee_id == employee_id,
                EmployeeBreak.date == query_date,
            )
        ).all()
        break_sessions = []
        for b in breaks:
            b_start = b.break_start
            b_end = b.break_end or now_utc
            break_sessions.append((b_start, b_end))

        # 3. Fetch Task Work Sessions starting within IST boundaries converted to UTC
        day_start, day_end = get_day_boundaries_utc(query_date)
        sessions = db.scalars(
            select(TaskWorkSession).where(
                TaskWorkSession.employee_id == employee_id,
                TaskWorkSession.start_time >= day_start,
                TaskWorkSession.start_time <= day_end,
            )
        ).all()

        task_sessions = []
        for s in sessions:
            s_start = s.start_time
            s_end = s.end_time
            if s.status == "RUNNING" and not s_end:
                s_end = now_utc
            elif not s_end:
                s_end = s_start + timedelta(minutes=(s.duration_minutes or 0))
            task_sessions.append((s_start, s_end))

        # Calculate using consistent processing order
        clamped_breaks = []
        for b_start, b_end in break_sessions:
            start_c = max(b_start, cin)
            end_c = min(b_end, cout)
            if start_c < end_c:
                clamped_breaks.append((start_c, end_c))
        merged_breaks = cls.merge_intervals(clamped_breaks)
        break_seconds = sum(int((end - start).total_seconds()) for start, end in merged_breaks)

        productive_seconds = cls.process_intervals(cin, cout, task_sessions, break_sessions)

        # Compute paused and waiting seconds from TaskPauseHistory
        stmt_pauses = (
            select(TaskPauseHistory)
            .join(Task)
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.employee_id == employee_id,
                TaskAssignment.status != "CANCELLED",
            )
        )
        pauses = db.scalars(stmt_pauses).all()

        pause_intervals = []
        waiting_intervals = []
        for p in pauses:
            p_start = p.paused_at
            p_end = p.resumed_at or now_utc
            start_clamp = max(p_start, cin)
            end_clamp = min(p_end, cout)
            if start_clamp < end_clamp:
                reason_str = (p.reason or "").lower()
                is_waiting = any(w in reason_str for w in ["waiting customer", "waiting information", "waiting review", "waiting"])
                if is_waiting:
                    waiting_intervals.append((start_clamp, end_clamp))
                else:
                    pause_intervals.append((start_clamp, end_clamp))

        merged_pauses = cls.merge_intervals(pause_intervals)
        merged_waiting = cls.merge_intervals(waiting_intervals)
        paused_seconds = sum(int((end - start).total_seconds()) for start, end in merged_pauses)
        waiting_seconds = sum(int((end - start).total_seconds()) for start, end in merged_waiting)

        return {
            "presence_seconds": presence_seconds,
            "break_seconds": break_seconds,
            "productive_seconds": productive_seconds,
            "paused_seconds": paused_seconds,
            "waiting_seconds": waiting_seconds,
        }

    @classmethod
    def calculate_raw_metrics_batch(
        cls,
        db: Session,
        employee_ids: list[uuid.UUID],
        query_date: date,
        now_utc: datetime
    ) -> dict[uuid.UUID, dict[str, int]]:
        """Compute presence, break, and productive seconds in a single batch query for multiple employees."""
        if not employee_ids:
            return {}

        # 1. Fetch Attendance records
        attendances = {
            att.employee_id: att
            for att in db.scalars(
                select(Attendance).where(
                    Attendance.employee_id.in_(employee_ids),
                    Attendance.date == query_date,
                )
            ).all()
        }

        # 2. Fetch Break records
        breaks = db.scalars(
            select(EmployeeBreak).where(
                EmployeeBreak.employee_id.in_(employee_ids),
                EmployeeBreak.date == query_date,
            )
        ).all()
        breaks_by_emp = {}
        for b in breaks:
            breaks_by_emp.setdefault(b.employee_id, []).append(b)

        # 3. Fetch Task Work Sessions
        day_start, day_end = get_day_boundaries_utc(query_date)
        sessions = db.scalars(
            select(TaskWorkSession).where(
                TaskWorkSession.employee_id.in_(employee_ids),
                TaskWorkSession.start_time >= day_start,
                TaskWorkSession.start_time <= day_end,
            )
        ).all()
        sessions_by_emp = {}
        for s in sessions:
            sessions_by_emp.setdefault(s.employee_id, []).append(s)

        results = {}
        for emp_id in employee_ids:
            attendance = attendances.get(emp_id)
            if not attendance or not attendance.clock_in:
                results[emp_id] = {
                    "presence_seconds": 0,
                    "break_seconds": 0,
                    "productive_seconds": 0,
                }
                continue

            cin = attendance.clock_in
            cout = attendance.clock_out
            presence_seconds = max(0, int(((cout or now_utc) - cin).total_seconds()))
            cout = cout or now_utc

            break_sessions = []
            for b in breaks_by_emp.get(emp_id, []):
                break_sessions.append((b.break_start, b.break_end or now_utc))

            task_sessions = []
            for s in sessions_by_emp.get(emp_id, []):
                s_start = s.start_time
                s_end = s.end_time
                if s.status == "RUNNING" and not s_end:
                    s_end = now_utc
                elif not s_end:
                    s_end = s_start + timedelta(minutes=(s.duration_minutes or 0))
                task_sessions.append((s_start, s_end))

            clamped_breaks = []
            for b_start, b_end in break_sessions:
                start_c = max(b_start, cin)
                end_c = min(b_end, cout)
                if start_c < end_c:
                    clamped_breaks.append((start_c, end_c))
            merged_breaks = cls.merge_intervals(clamped_breaks)
            break_seconds = sum(int((end - start).total_seconds()) for start, end in merged_breaks)

            productive_seconds = cls.process_intervals(cin, cout, task_sessions, break_sessions)

            results[emp_id] = {
                "presence_seconds": presence_seconds,
                "break_seconds": break_seconds,
                "productive_seconds": productive_seconds,
            }
        return results

    @classmethod
    def verify_kpi_invariants(cls, raw: dict[str, int], compiled: dict[str, dict[str, Any]]) -> None:
        """
        Validate mathematical invariants of EWPE productivity formulas.
        Asserts rules such as:
        1. Presence >= Break
        2. Presence >= Productive
        3. Organization = Presence - Break
        4. Organization = Productive + Idle + Paused + Waiting
        """
        presence = compiled["presence_time"]["raw_seconds"]
        breaks = compiled["break_time"]["raw_seconds"]
        productive = compiled["productive_time"]["raw_seconds"]
        org = compiled["organization_time"]["raw_seconds"]
        idle = compiled["idle_time"]["raw_seconds"]
        paused = compiled.get("paused_time", {}).get("raw_seconds", 0)
        waiting = compiled.get("waiting_time", {}).get("raw_seconds", 0)

        if not (presence >= breaks):
            raise ValueError(f"Invariant Violation: Presence ({presence}s) < Break ({breaks}s)")
        if not (presence >= productive):
            raise ValueError(f"Invariant Violation: Presence ({presence}s) < Productive ({productive}s)")
        if not (org == presence - breaks):
            raise ValueError(f"Invariant Violation: Org ({org}s) != Presence ({presence}s) - Break ({breaks}s)")
        if not (org == productive + idle + paused + waiting):
            raise ValueError(f"Invariant Violation: Org ({org}s) != Productive ({productive}s) + Idle ({idle}s) + Paused ({paused}s) + Waiting ({waiting}s)")

    @classmethod
    def compile_kpi_metrics(
        cls,
        raw: dict[str, int],
        rule: AttendanceRule
    ) -> dict[str, dict[str, Any]]:
        """Run standard formulas to construct the 11 KPI metrics dictionary."""
        presence = raw["presence_seconds"]
        breaks = min(presence, raw["break_seconds"])
        org = presence - breaks
        productive = min(org, raw["productive_seconds"])
        paused = raw.get("paused_seconds", 0)
        waiting = raw.get("waiting_seconds", 0)
        idle = max(0, org - productive - paused - waiting)

        req_hours = float(rule.required_productive_hours)
        req_seconds = int(req_hours * 3600)
        remaining = max(0, req_seconds - org)

        prod_pct = (productive / org * 100) if org > 0 else 0.0
        org_util = (org / presence * 100) if presence > 0 else 0.0
        att_util = (productive / presence * 100) if presence > 0 else 0.0
        break_pct = (breaks / presence * 100) if presence > 0 else 0.0
        idle_pct = (idle / presence * 100) if presence > 0 else 0.0

        compiled_metrics = {
            "presence_time": cls.make_kpi_object(
                "Presence Time", presence, formula="Clock Out - Clock In"
            ),
            "break_time": cls.make_kpi_object(
                "Break Time", breaks, formula="Sum of Break Durations", rule=rule
            ),
            "organization_time": cls.make_kpi_object(
                "Organization Time", org, formula="Presence - Break"
            ),
            "productive_time": cls.make_kpi_object(
                "Productive Time", productive, expected_seconds=req_seconds, formula="Sum of Task Sessions", rule=rule
            ),
            "idle_time": cls.make_kpi_object(
                "Idle Time", idle, formula="Organization - Productive"
            ),
            "remaining_productive_time": cls.make_kpi_object(
                "Remaining Productive Time", remaining, formula="Required Hours - Organization"
            ),
            "productivity_percentage": cls.make_kpi_object(
                "Productivity %", 0, percentage_override=prod_pct, formula="Productive / Organization * 100"
            ),
            "organization_utilization": cls.make_kpi_object(
                "Organization Utilization %", 0, percentage_override=org_util, formula="Organization / Presence * 100"
            ),
            "attendance_utilization": cls.make_kpi_object(
                "Attendance Utilization %", 0, percentage_override=att_util, formula="Productive / Presence * 100"
            ),
            "break_percentage": cls.make_kpi_object(
                "Break %", 0, percentage_override=break_pct, formula="Break / Presence * 100"
            ),
            "idle_percentage": cls.make_kpi_object(
                "Idle %", 0, percentage_override=idle_pct, formula="Idle / Presence * 100"
            ),
            "paused_time": cls.make_kpi_object(
                "Paused Time", paused, formula="Sum of Task Paused Durations"
            ),
            "waiting_time": cls.make_kpi_object(
                "Waiting Time", waiting, formula="Sum of Task Waiting Durations"
            ),
        }

        # Enforce mathematical invariants
        cls.verify_kpi_invariants(raw, compiled_metrics)

        return compiled_metrics

    @staticmethod
    def calculate_trend(current: float, previous: float) -> dict[str, Any]:
        """Compute the trend percentage and direction indicators."""
        if previous == 0:
            change = 0.0
            direction = "flat"
        else:
            change = round(((current - previous) / previous) * 100, 1)
            direction = "up" if change > 0 else ("down" if change < 0 else "flat")

        formatted_change = f"{change:+.1f}%" if change != 0 else "0.0%"

        return {
            "current_value": current,
            "previous_value": previous,
            "change_percentage": formatted_change,
            "direction": direction,
        }
