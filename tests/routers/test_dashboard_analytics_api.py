from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.dashboard.executive_dashboard_service import ExecutiveDashboardService
from app.services.dashboard.project_dashboard_service import ProjectDashboardService
from app.services.dashboard.team_leader_dashboard_service import TeamLeaderDashboardService
from app.services.dashboard.employee_dashboard_service import EmployeeDashboardService
from app.services.dashboard.employee_performance_service import EmployeePerformanceService
from app.schemas.dashboard_analytics import (
    ExecutiveSummary,
    ExecutiveCharts,
    ExecutiveAlerts,
    ExecutiveRecentActivities,
    ProjectSummary,
    ProjectCharts,
    TeamLeadSummary,
    TeamLeadCharts,
    EmployeeSummary,
    EmployeeCharts
)

TEST_PROJECT_ID = uuid4()

class TestDashboardAnalyticsApi:
    @pytest.mark.asyncio
    async def test_executive_summary(self, async_client):
        with patch.object(ExecutiveDashboardService, "get_summary") as mock_svc:
            mock_svc.return_value = ExecutiveSummary(
                total_projects=5,
                active_projects=2,
                completed_projects=3,
                delayed_projects=0,
                company_utilization_percentage=75.5
            )

            resp = await async_client.get("/api/v1/dashboard-analytics/executive/summary")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["data"]["totalProjects"] == 5

    @pytest.mark.asyncio
    async def test_executive_charts(self, async_client):
        with patch.object(ExecutiveDashboardService, "get_charts") as mock_svc:
            mock_svc.return_value = ExecutiveCharts(
                project_statuses=[],
                department_performances=[]
            )

            resp = await async_client.get("/api/v1/dashboard-analytics/executive/charts")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True

    @pytest.mark.asyncio
    async def test_executive_alerts(self, async_client):
        with patch.object(ExecutiveDashboardService, "get_alerts") as mock_svc:
            mock_svc.return_value = ExecutiveAlerts(alerts=[])

            resp = await async_client.get("/api/v1/dashboard-analytics/executive/alerts")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True

    @pytest.mark.asyncio
    async def test_project_summary(self, async_client):
        with patch.object(ProjectDashboardService, "get_summary") as mock_svc:
            mock_svc.return_value = ProjectSummary(
                id=TEST_PROJECT_ID,
                project_code="PRJ-001",
                name="Test Project",
                planned_hours=100.0,
                actual_hours=50.0,
                remaining_hours=50.0,
                completion_percentage=50.0,
                total_tasks=10,
                completed_tasks=5,
                in_progress_tasks=5
            )

            resp = await async_client.get(f"/api/v1/dashboard-analytics/project/{TEST_PROJECT_ID}/summary")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["data"]["projectCode"] == "PRJ-001"

    @pytest.mark.asyncio
    async def test_team_leader_summary(self, async_client):
        with patch.object(TeamLeaderDashboardService, "get_summary") as mock_svc:
            mock_svc.return_value = TeamLeadSummary(
                total_team_members=3,
                today_attendance_count=3,
                pending_approvals_count=0
            )

            resp = await async_client.get("/api/v1/dashboard-analytics/team-leader/summary")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True

    @pytest.mark.asyncio
    async def test_employee_summary(self, async_client):
        with patch.object(EmployeeDashboardService, "get_summary") as mock_svc:
            mock_svc.return_value = EmployeeSummary(
                today_tasks_count=2,
                today_hours=8.0,
                weekly_hours=40.0,
                personal_productivity_percentage=95.0
            )

            resp = await async_client.get("/api/v1/dashboard-analytics/employee/summary")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True

    @pytest.mark.asyncio
    async def test_performance_rankings(self, async_client):
        with patch.object(EmployeePerformanceService, "get_rankings") as mock_svc:
            mock_svc.return_value = []

            resp = await async_client.get("/api/v1/dashboard-analytics/performance/rankings")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
