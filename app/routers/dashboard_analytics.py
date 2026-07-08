import json
from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
import io
import csv

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission, require_any_permission
from app.core.rbac import UserContext, require_data_access, DataAccessLevel
from app.schemas.common import APIResponse
from app.services.dashboard.executive_dashboard_service import ExecutiveDashboardService
from app.services.dashboard.project_dashboard_service import ProjectDashboardService
from app.services.dashboard.team_leader_dashboard_service import TeamLeaderDashboardService
from app.services.dashboard.employee_dashboard_service import EmployeeDashboardService
from app.services.dashboard.employee_performance_service import EmployeePerformanceService
from app.core.redis import get_cache, set_cache

router = APIRouter(
    prefix="/dashboard-analytics",
    tags=["Dashboard Analytics"],
    dependencies=[Depends(get_current_user)],
)

# --- Executive Dashboard Router ---
@router.get(
    "/executive/summary",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Analytics", "view"))]
)
def get_executive_summary(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:executive:summary:{user_ctx.employee_id}:from:{from_date}:to:{to_date}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Executive summary retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = ExecutiveDashboardService(db)
    res = svc.get_summary(from_date, to_date, user_ctx=user_ctx)
    data = res.model_dump(mode="json", by_alias=True)
    set_cache(key, json.dumps(data), ttl=30)
    return APIResponse(success=True, message="Executive summary retrieved", data=data)

@router.get(
    "/executive/charts",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Analytics", "view"))]
)
def get_executive_charts(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:executive:charts:{user_ctx.employee_id}:from:{from_date}:to:{to_date}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Executive charts retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = ExecutiveDashboardService(db)
    res = svc.get_charts(from_date, to_date, user_ctx=user_ctx)
    data = res.model_dump(mode="json", by_alias=True)
    set_cache(key, json.dumps(data), ttl=60)
    return APIResponse(success=True, message="Executive charts retrieved", data=data)

@router.get(
    "/executive/alerts",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Analytics", "view"))]
)
def get_executive_alerts(
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:executive:alerts:{user_ctx.employee_id}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Executive alerts retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = ExecutiveDashboardService(db)
    res = svc.get_alerts(user_ctx=user_ctx)
    data = res.model_dump(mode="json", by_alias=True)
    set_cache(key, json.dumps(data), ttl=30)
    return APIResponse(success=True, message="Executive alerts retrieved", data=data)

@router.get(
    "/executive/recent-projects",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Analytics", "view"))]
)
def get_executive_recent_projects(
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:executive:recent-projects:{user_ctx.employee_id}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Recent projects retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = ExecutiveDashboardService(db)
    projects = svc.get_recent_projects(user_ctx=user_ctx)
    data = [
        {
            "id": str(p.id),
            "projectCode": p.project_code,
            "name": p.name,
            "status": p.status,
            "progress": float(p.progress),
            "plannedEndDate": p.planned_end_date.isoformat() if p.planned_end_date else None
        }
        for p in projects
    ]
    res_data = {"projects": data}
    set_cache(key, json.dumps(res_data), ttl=30)
    return APIResponse(success=True, message="Recent projects retrieved", data=res_data)

@router.get(
    "/executive/recent-activities",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Analytics", "view"))]
)
def get_executive_recent_activities(
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:executive:recent-activities:{user_ctx.employee_id}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Recent activities retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = ExecutiveDashboardService(db)
    res = svc.get_recent_activities(user_ctx=user_ctx)
    data = res.model_dump(mode="json", by_alias=True)
    set_cache(key, json.dumps(data), ttl=30)
    return APIResponse(success=True, message="Recent activities retrieved", data=data)


# --- Executive Tabbed Drilldown Routers ---
@router.get(
    "/executive/team-performance",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Analytics", "view"))]
)
def get_executive_team_performance(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:executive:team-perf:{user_ctx.employee_id}:from:{from_date}:to:{to_date}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Executive team performance retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = ExecutiveDashboardService(db)
    res = svc.get_team_performance(from_date, to_date, user_ctx=user_ctx)
    data = res.model_dump(mode="json", by_alias=True)
    set_cache(key, json.dumps(data), ttl=30)
    return APIResponse(success=True, message="Executive team performance retrieved", data=data)

@router.get(
    "/executive/client-performance",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Analytics", "view"))]
)
def get_executive_client_performance(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:executive:client-perf:{user_ctx.employee_id}:from:{from_date}:to:{to_date}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Executive client performance retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = ExecutiveDashboardService(db)
    res = svc.get_client_performance_exec(from_date, to_date, user_ctx=user_ctx)
    data = res.model_dump(mode="json", by_alias=True)
    set_cache(key, json.dumps(data), ttl=30)
    return APIResponse(success=True, message="Executive client performance retrieved", data=data)

@router.get(
    "/executive/individual-performance",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Analytics", "view"))]
)
def get_executive_individual_performance(
    department_id: UUID | None = Query(None),
    team_id: UUID | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:executive:indiv-perf:{user_ctx.employee_id}:dept:{department_id}:team:{team_id}:from:{from_date}:to:{to_date}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Executive individual performance retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = ExecutiveDashboardService(db)
    rankings = svc.get_individual_performance(department_id, team_id, from_date, to_date, user_ctx=user_ctx)
    data = {"rankings": [r.model_dump(mode="json", by_alias=True) for r in rankings]}
    set_cache(key, json.dumps(data), ttl=30)
    return APIResponse(success=True, message="Executive individual performance retrieved", data=data)

@router.get(
    "/executive/project-list",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Analytics", "view"))]
)
def get_executive_project_list(
    department_id: UUID | None = Query(None),
    team_id: UUID | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:executive:proj-list:{user_ctx.employee_id}:dept:{department_id}:team:{team_id}:from:{from_date}:to:{to_date}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Executive project list retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = ExecutiveDashboardService(db)
    res = svc.get_project_list(department_id, team_id, from_date, to_date, user_ctx=user_ctx)
    data = res.model_dump(mode="json", by_alias=True)
    set_cache(key, json.dumps(data), ttl=30)
    return APIResponse(success=True, message="Executive project list retrieved", data=data)

@router.get(
    "/executive/task-summary",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Analytics", "view"))]
)
def get_executive_task_summary(
    department_id: UUID | None = Query(None),
    team_id: UUID | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:executive:task-summary:{user_ctx.employee_id}:dept:{department_id}:team:{team_id}:from:{from_date}:to:{to_date}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Executive task summary retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = ExecutiveDashboardService(db)
    res = svc.get_task_summary(department_id, team_id, from_date, to_date, user_ctx=user_ctx)
    data = res.model_dump(mode="json", by_alias=True)
    set_cache(key, json.dumps(data), ttl=30)
    return APIResponse(success=True, message="Executive task summary retrieved", data=data)



# --- Project Dashboard Router ---
@router.get(
    "/project/{project_id}/summary",
    response_model=APIResponse,
    dependencies=[Depends(require_any_permission(("Analytics", "view"), ("Projects", "view")))],
)
def get_project_summary(
    project_id: UUID,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    # Security H8 (IDOR): enforce project membership for ALL non-FULL access
    # levels (SELF, TEAM, MANAGED) so mid-tier users cannot read arbitrary
    # projects by id. Only FULL (admin/CEO) bypasses the membership check.
    if user_ctx.data_access_level != DataAccessLevel.FULL:
        from app.models.project_member import ProjectMember
        is_assigned = db.scalar(
            select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.employee_id == user_ctx.employee_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: You are not assigned to this project.")

    key = f"erp:dashboard:project:{project_id}:summary"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Project summary retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = ProjectDashboardService(db)
    try:
        res = svc.get_summary(project_id)
        data = res.model_dump(mode="json", by_alias=True)
        set_cache(key, json.dumps(data), ttl=15)
        return APIResponse(success=True, message="Project summary retrieved", data=data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.get(
    "/project/{project_id}/charts",
    response_model=APIResponse,
    dependencies=[Depends(require_any_permission(("Analytics", "view"), ("Projects", "view")))],
)
def get_project_charts(
    project_id: UUID,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    # Security H8 (IDOR): enforce project membership for ALL non-FULL access
    # levels (SELF, TEAM, MANAGED). Only FULL (admin/CEO) bypasses the check.
    if user_ctx.data_access_level != DataAccessLevel.FULL:
        from app.models.project_member import ProjectMember
        is_assigned = db.scalar(
            select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.employee_id == user_ctx.employee_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    key = f"erp:dashboard:project:{project_id}:charts"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Project charts retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = ProjectDashboardService(db)
    try:
        res = svc.get_charts(project_id)
        data = res.model_dump(mode="json", by_alias=True)
        set_cache(key, json.dumps(data), ttl=60)
        return APIResponse(success=True, message="Project charts retrieved", data=data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# --- Team Leader Dashboard Router ---
@router.get(
    "/team-leader/summary",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Dashboard", "view"))],
)
def get_team_lead_summary(
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:team-leader:{user_ctx.employee_id}:summary"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Team leader summary retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = TeamLeaderDashboardService(db)
    res = svc.get_summary(user_ctx.employee_id)
    data = res.model_dump(mode="json", by_alias=True)
    set_cache(key, json.dumps(data), ttl=30)
    return APIResponse(success=True, message="Team leader summary retrieved", data=data)

@router.get(
    "/team-leader/charts",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Dashboard", "view"))],
)
def get_team_lead_charts(
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:team-leader:{user_ctx.employee_id}:charts"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Team leader charts retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = TeamLeaderDashboardService(db)
    res = svc.get_charts(user_ctx.employee_id)
    data = res.model_dump(mode="json", by_alias=True)
    set_cache(key, json.dumps(data), ttl=30)
    return APIResponse(success=True, message="Team leader charts retrieved", data=data)

@router.get(
    "/team-leader/attendance",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Dashboard", "view"))],
)
def get_team_lead_attendance(
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    # Live data â€” NEVER cached
    svc = TeamLeaderDashboardService(db)
    res = svc.get_attendance(user_ctx.employee_id)
    return APIResponse(
        success=True,
        message="Team attendance retrieved",
        data={"attendance": [row.model_dump(mode="json", by_alias=True) for row in res]}
    )


# --- Employee Dashboard Router ---
@router.get(
    "/employee/summary",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Dashboard", "view"))],
)
def get_employee_summary(
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
):
    key = f"erp:dashboard:employee:{user_ctx.employee_id}:summary:from:{from_date}:to:{to_date}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Employee summary retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = EmployeeDashboardService(db)
    res = svc.get_summary(user_ctx.employee_id, from_date=from_date, to_date=to_date)
    data = res.model_dump(mode="json", by_alias=True)
    set_cache(key, json.dumps(data), ttl=5)
    return APIResponse(success=True, message="Employee summary retrieved", data=data)

@router.get(
    "/employee/charts",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Dashboard", "view"))],
)
def get_employee_charts(
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
):
    key = f"erp:dashboard:employee:{user_ctx.employee_id}:charts:from:{from_date}:to:{to_date}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Employee charts retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = EmployeeDashboardService(db)
    res = svc.get_charts(user_ctx.employee_id, from_date=from_date, to_date=to_date)
    data = res.model_dump(mode="json", by_alias=True)
    set_cache(key, json.dumps(data), ttl=5)
    return APIResponse(success=True, message="Employee charts retrieved", data=data)


# --- Employee Performance Dashboard Router ---
@router.get(
    "/performance/rankings",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("HR", "view"))]
)
def get_performance_rankings(
    department_id: UUID | None = Query(None),
    team_id: UUID | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    key = f"erp:dashboard:performance:rankings:{user_ctx.employee_id}:dept:{department_id}:team:{team_id}:from:{from_date}:to:{to_date}"
    cached = get_cache(key)
    if cached:
        try:
            return APIResponse(success=True, message="Performance rankings retrieved (cached)", data=json.loads(cached))
        except Exception:
            pass

    svc = EmployeePerformanceService(db)
    rankings = svc.get_rankings(department_id, team_id, from_date, to_date, user_ctx=user_ctx)
    data = {"rankings": [row.model_dump(mode="json", by_alias=True) for row in rankings]}
    set_cache(key, json.dumps(data), ttl=60)
    return APIResponse(success=True, message="Performance rankings retrieved", data=data)

@router.get(
    "/performance/export",
    dependencies=[Depends(require_permission("HR", "view"))]
)
def export_performance_rankings(
    department_id: UUID | None = Query(None),
    team_id: UUID | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    # Always fetch live ranks for export files
    svc = EmployeePerformanceService(db)
    rankings = svc.get_rankings(department_id, team_id, from_date, to_date, user_ctx=user_ctx)
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Rank", "Employee Code", "Employee Name", "Department", "Team",
        "Utilization %", "Planned Hours", "Actual Hours", "Variance",
        "Task Completion %", "Average Hours/Task", "Average Delay (Days)",
        "Rework Hours", "Productivity Score", "Efficiency Score", "Timesheet Compliance"
    ])
    
    for r in rankings:
        writer.writerow([
            r.performance_rank, r.employee_code, r.employee_name, r.department_name or "-", r.team_name or "-",
            r.utilization_percentage, r.planned_hours, r.actual_hours, r.variance_hours,
            r.task_completion_percentage, r.average_hours_per_task, r.average_delay_days,
            r.rework_hours, r.productivity_score, r.efficiency_score, r.timesheet_compliance_score
        ])
        
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employee_performance_rankings.csv"}
    )


# --- Employee Load Chart ---
@router.get(
    "/employee-load",
    response_model=APIResponse,
    dependencies=[Depends(require_any_permission(("Dashboard", "view"), ("Analytics", "view")))],
)
def get_employee_load_chart(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    department_id: UUID | None = Query(None),
    team_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access),
):
    """
    Returns hierarchical employee load data formatted for a Gantt chart.
    Respects role-based data scoping (SELF/TEAM/MANAGED/FULL).
    """
    from datetime import timedelta

    if not from_date:
        from_date = date.today()
    if not to_date:
        to_date = from_date + timedelta(days=90)

    from app.services.planning_service import PlanningService
    svc = PlanningService(db, current_user_id=user_ctx.employee_id)
    rows = svc.get_employee_load_chart(
        requesting_employee_id=user_ctx.employee_id,
        from_date=from_date,
        to_date=to_date,
        department_id=department_id,
        team_id=team_id,
    )
    return APIResponse(
        success=True,
        message="Employee load chart retrieved",
        data={
            "rows": rows,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
        },
    )
