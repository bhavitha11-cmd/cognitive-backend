from datetime import date, datetime, timezone, timedelta
from collections import defaultdict
from typing import Any, Optional
import uuid
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.employee_break import EmployeeBreak
from app.models.task_work_session import TaskWorkSession
from app.models.attendance_rule import AttendanceRule
from app.services.productivity.kpi_calculator import KPICalculator, IST



class ReportAggregator:
    @classmethod
    def get_employee_range_metrics(
        cls,
        db: Session,
        employee_id: uuid.UUID,
        start_date: date,
        end_date: date,
        rule: AttendanceRule,
        now_utc: datetime
    ) -> dict[str, Any]:
        """Aggregate productivity metrics for a single employee over a date range."""
        # 1. Fetch raw metrics for each day in range using bulk queries
        raw_by_date = cls.get_bulk_raw_metrics(db, [employee_id], start_date, end_date, now_utc)

        daily_summaries = []
        tot_presence = 0
        tot_break = 0
        tot_productive = 0

        curr = start_date
        while curr <= end_date:
            day_raw = raw_by_date[(employee_id, curr)]
            tot_presence += day_raw["presence_seconds"]
            tot_break += day_raw["break_seconds"]
            tot_productive += day_raw["productive_seconds"]

            day_kpis = KPICalculator.compile_kpi_metrics(day_raw, rule)
            daily_summaries.append({
                "date": curr.isoformat(),
                "kpis": day_kpis
            })
            curr += timedelta(days=1)

        # Calculate aggregated period KPIs
        agg_raw = {
            "presence_seconds": tot_presence,
            "break_seconds": tot_break,
            "productive_seconds": tot_productive,
        }
        period_kpis = KPICalculator.compile_kpi_metrics(agg_raw, rule)

        return {
            "employee_id": str(employee_id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "period_kpis": period_kpis,
            "days": daily_summaries
        }

    @classmethod
    def get_bulk_raw_metrics(
        cls,
        db: Session,
        employee_ids: list[uuid.UUID],
        start_date: date,
        end_date: date,
        now_utc: datetime
    ) -> dict[tuple[uuid.UUID, date], dict[str, int]]:
        """Fetch presence, breaks, and task session seconds in bulk to avoid N+1 query patterns."""
        raw_metrics = defaultdict(lambda: {
            "presence_seconds": 0,
            "break_seconds": 0,
            "productive_seconds": 0
        })

        if not employee_ids:
            return raw_metrics

        # 1. Bulk Attendance Query
        attendances = db.scalars(
            select(Attendance).where(
                and_(
                    Attendance.employee_id.in_(employee_ids),
                    Attendance.date >= start_date,
                    Attendance.date <= end_date
                )
            )
        ).all()

        # 2. Bulk Breaks Query
        breaks = db.scalars(
            select(EmployeeBreak).where(
                and_(
                    EmployeeBreak.employee_id.in_(employee_ids),
                    EmployeeBreak.date >= start_date,
                    EmployeeBreak.date <= end_date
                )
            )
        ).all()

        breaks_by_emp_date = defaultdict(list)
        for b in breaks:
            b_start = b.break_start
            b_end = b.break_end or now_utc
            breaks_by_emp_date[(b.employee_id, b.date)].append((b_start, b_end))

        # 3. Bulk Task Sessions Query using IST day boundaries in UTC
        day_start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=IST).astimezone(timezone.utc)
        day_end = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=IST).astimezone(timezone.utc)
        
        sessions = db.scalars(
            select(TaskWorkSession).where(
                and_(
                    TaskWorkSession.employee_id.in_(employee_ids),
                    TaskWorkSession.start_time >= day_start,
                    TaskWorkSession.start_time <= day_end
                )
            )
        ).all()

        sessions_by_emp_date = defaultdict(list)
        for s in sessions:
            s_start = s.start_time
            s_end = s.end_time
            s_date = s_start.date()
            if s.status == "RUNNING" and not s_end:
                s_end = now_utc
            elif not s_end:
                s_end = s_start + timedelta(minutes=(s.duration_minutes or 0))
            sessions_by_emp_date[(s.employee_id, s_date)].append((s_start, s_end))

        # Calculate raw metrics consistently
        for att in attendances:
            cin = att.clock_in
            cout = att.clock_out
            if cin:
                if cout:
                    dur = int((cout - cin).total_seconds())
                else:
                    if att.date == now_utc.date():
                        dur = int((now_utc - cin).total_seconds())
                    else:
                        dur = 0
                presence_seconds = max(0, dur)

                emp_breaks = breaks_by_emp_date[(att.employee_id, att.date)]
                emp_sessions = sessions_by_emp_date[(att.employee_id, att.date)]

                # Process breaks (clamped to presence and merged)
                clamped_breaks = []
                for b_start, b_end in emp_breaks:
                    start_c = max(b_start, cin)
                    end_c = min(b_end, cout or now_utc)
                    if start_c < end_c:
                        clamped_breaks.append((start_c, end_c))
                merged_breaks = KPICalculator.merge_intervals(clamped_breaks)
                break_seconds = sum(int((end - start).total_seconds()) for start, end in merged_breaks)

                # Process task sessions with consistent order
                productive_seconds = KPICalculator.process_intervals(
                    cin, cout or now_utc, emp_sessions, emp_breaks
                )

                raw_metrics[(att.employee_id, att.date)] = {
                    "presence_seconds": presence_seconds,
                    "break_seconds": break_seconds,
                    "productive_seconds": productive_seconds
                }

        return raw_metrics

    @classmethod
    def get_bulk_productivity_report(
        cls,
        db: Session,
        employee_ids: list[uuid.UUID],
        start_date: date,
        end_date: date,
        rule: AttendanceRule,
        now_utc: datetime
    ) -> list[dict[str, Any]]:
        """Fetch range KPIs for a list of employees in a single batch of DB queries."""
        raw_by_date = cls.get_bulk_raw_metrics(db, employee_ids, start_date, end_date, now_utc)

        results = []
        for emp_id in employee_ids:
            daily_summaries = []
            tot_presence = 0
            tot_break = 0
            tot_productive = 0

            curr = start_date
            while curr <= end_date:
                day_raw = raw_by_date[(emp_id, curr)]
                tot_presence += day_raw["presence_seconds"]
                tot_break += day_raw["break_seconds"]
                tot_productive += day_raw["productive_seconds"]

                day_kpis = KPICalculator.compile_kpi_metrics(day_raw, rule)
                daily_summaries.append({
                    "date": curr.isoformat(),
                    "kpis": day_kpis
                })
                curr += timedelta(days=1)

            agg_raw = {
                "presence_seconds": tot_presence,
                "break_seconds": tot_break,
                "productive_seconds": tot_productive,
            }
            period_kpis = KPICalculator.compile_kpi_metrics(agg_raw, rule)

            results.append({
                "employee_id": str(emp_id),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "period_kpis": period_kpis,
                "days": daily_summaries
            })
        return results
