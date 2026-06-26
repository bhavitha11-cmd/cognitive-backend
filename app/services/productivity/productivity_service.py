from datetime import date, datetime, timezone, timedelta
from typing import Any, Optional
import uuid
from sqlalchemy.orm import Session

from app.models.idle_classification import IdleClassification
from app.models.idle_reason_master import IdleReasonMaster
from app.services.productivity.policy_resolver import PolicyResolver
from app.services.productivity.kpi_calculator import KPICalculator
from app.services.productivity.timeline_builder import TimelineBuilder
from app.services.productivity.idle_analyzer import IdleAnalyzer
from app.services.productivity.report_aggregator import ReportAggregator


class WorkforceProductivityService:
    def __init__(self, db: Session, current_user_id: uuid.UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    def get_today_kpis(self, employee_id: uuid.UUID) -> dict[str, Any]:
        """Fetch today's productivity KPIs for the employee, enriched with yesterday's trend analysis."""
        now_utc = datetime.now(timezone.utc)
        today = now_utc.date()
        yesterday = today - timedelta(days=1)

        rule = PolicyResolver.get_rule(self.db)

        # 1. Calculate today's raw and compiled metrics
        today_raw = KPICalculator.calculate_raw_metrics(self.db, employee_id, today, now_utc)
        today_kpis = KPICalculator.compile_kpi_metrics(today_raw, rule)

        # 2. Calculate yesterday's raw and compiled metrics (for trend analysis)
        yesterday_raw = KPICalculator.calculate_raw_metrics(self.db, employee_id, yesterday, now_utc)
        yesterday_kpis = KPICalculator.compile_kpi_metrics(yesterday_raw, rule)

        # 3. Enrich today's KPIs with trends
        enriched_kpis = {}
        for key, kpi in today_kpis.items():
            yesterday_kpi = yesterday_kpis.get(key)
            if yesterday_kpi:
                curr_val = kpi["hours"] if "percentage" not in key else kpi["percentage"]
                prev_val = yesterday_kpi["hours"] if "percentage" not in key else yesterday_kpi["percentage"]
                trend = KPICalculator.calculate_trend(curr_val, prev_val)
            else:
                trend = {
                    "current_value": kpi["hours"] if "percentage" not in key else kpi["percentage"],
                    "previous_value": 0.0,
                    "change_percentage": "0.0%",
                    "direction": "flat"
                }
            
            kpi_copy = dict(kpi)
            kpi_copy["trend"] = trend
            enriched_kpis[key] = kpi_copy

        return {
            "employee_id": str(employee_id),
            "date": today.isoformat(),
            "kpis": enriched_kpis
        }

    def get_timeline(self, employee_id: uuid.UUID, query_date: date) -> list[dict[str, Any]]:
        """Reconstruct activity timeline for employee on query_date."""
        now_utc = datetime.now(timezone.utc)
        return TimelineBuilder.build_daily_timeline(self.db, employee_id, query_date, now_utc)

    def get_active_reasons(self, department_id: uuid.UUID | None = None) -> list[IdleReasonMaster]:
        """Fetch all active idle reasons for a department or global."""
        return IdleAnalyzer.get_active_reasons(self.db, department_id)

    def classify_idle_segment(
        self,
        employee_id: uuid.UUID,
        query_date: date,
        idle_segment_identifier: str,
        reason_id: uuid.UUID,
        remarks: str | None = None
    ) -> IdleClassification:
        """Tag an idle segment with a classification reason."""
        return IdleAnalyzer.classify_idle_segment(
            db=self.db,
            employee_id=employee_id,
            query_date=query_date,
            idle_segment_identifier=idle_segment_identifier,
            reason_id=reason_id,
            remarks=remarks,
            performed_by_id=self.current_user_id
        )

    def get_employee_range_metrics(
        self,
        employee_id: uuid.UUID,
        start_date: date,
        end_date: date
    ) -> dict[str, Any]:
        """Aggregate range-based KPIs for an employee."""
        now_utc = datetime.now(timezone.utc)
        rule = PolicyResolver.get_rule(self.db)
        return ReportAggregator.get_employee_range_metrics(
            self.db, employee_id, start_date, end_date, rule, now_utc
        )

    def get_bulk_productivity_report(
        self,
        employee_ids: list[uuid.UUID],
        start_date: date,
        end_date: date
    ) -> list[dict[str, Any]]:
        """Fetch range KPIs for a list of employees in bulk (for HR or managers dashboard)."""
        now_utc = datetime.now(timezone.utc)
        rule = PolicyResolver.get_rule(self.db)
        return ReportAggregator.get_bulk_productivity_report(
            self.db, employee_ids, start_date, end_date, rule, now_utc
        )
