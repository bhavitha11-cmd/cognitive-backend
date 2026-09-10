import logging
import re
import sys
import time
import traceback
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.database.connection import engine
from app.core.config import settings
from app.routers.role import router as role_router
from app.routers.department import router as department_router
from app.routers.designation import router as designation_router
from app.routers.employee import router as employee_router
from app.routers.team import router as team_router
from app.routers.organization import router as organization_router
from app.routers.audit import router as audit_router
from app.routers.auth import router as auth_router
from app.routers.client import router as client_router
from app.routers.scope_of_work import router as scope_of_work_router
from app.routers.parent_project import router as project_router
from app.routers.task import router as task_router
from app.routers.part import router as part_router
from app.routers.attendance import router as attendance_router
from app.routers.time_entry import router as time_entry_router
from app.routers.leave import router as leave_router
from app.routers.approval import router as approval_router
from app.routers.planning import router as planning_router
from app.routers.analytics import router as analytics_router
from app.routers.work_session import router as work_session_router
from app.routers.employee_break import router as employee_break_router
from app.routers.task_rework import router as task_rework_router
from app.routers.holiday import router as holiday_router
from app.routers.calendar_settings import router as calendar_settings_router
from app.routers.company_event import router as company_event_router
from app.routers.calendar import router as calendar_router
from app.routers.dashboard_widget import router as dashboard_widget_router
from app.routers.task_template import router as task_template_router
from app.routers.productivity import router as productivity_router
from app.routers.dashboard_analytics import router as dashboard_analytics_router
from app.routers.pending_schedule_review import router as schedule_review_router
from app.routers.modules import router as modules_router
from app.routers.email_configuration import router as email_configuration_router
from app.routers.ticket import router as ticket_router
import app.core.redis
from app.middleware.audit_context import set_audit_context
from app.routers.biometric import router as biometric_router
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ── Logging configuration ────────────────────────────────────────────────────
# Ensures ALL loggers (uvicorn.*, __name__, alembic, sqlalchemy, etc.) produce
# visible, consistently formatted output instead of relying on uvicorn's defaults.
# This is critical because many services use logging.getLogger(__name__) which
# would otherwise inherit root logger's default WARNING level and silently drop
# INFO messages.

LOG_LEVEL = logging.getLevelName(settings.LOG_LEVEL.upper()) if settings.LOG_LEVEL else (logging.DEBUG if settings.DEBUG else logging.INFO)

root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)

# Replace any pre-existing handlers (from uvicorn) with our own for consistent format
root_logger.handlers.clear()
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(LOG_LEVEL)
formatter = logging.Formatter(
    "%(asctime)s  %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

# Setup logging directory and file path
BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE_PATH = LOGS_DIR / "uvicorn_live.log"

file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
file_handler.setLevel(LOG_LEVEL)
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

# Make uvicorn's loggers use our root handler for consistent format
for log_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.default"):
    uvicorn_logger = logging.getLogger(log_name)
    uvicorn_logger.handlers.clear()
    uvicorn_logger.setLevel(LOG_LEVEL)
    uvicorn_logger.propagate = True

# Keep SQLAlchemy engine logs quiet unless DB_ECHO is on
logging.getLogger("sqlalchemy.engine").setLevel(logging.DEBUG if settings.DB_ECHO else logging.WARNING)

# Keep watchfiles log quiet to avoid cluttering console during development reload
logging.getLogger("watchfiles").setLevel(logging.WARNING)

# NOTE (rate limiting): This is the app-level Limiter bound to app.state.limiter
# and used by the RateLimitExceeded handler. Some routers (e.g. auth.py) currently
# construct their OWN Limiter(key_func=get_remote_address) instance for their
# @limiter.limit decorators. On a single server this works fine because each
# instance keeps its own in-memory counters and the shared exception handler
# formats the 429 response identically. Consolidating to one shared instance
# would require editing those routers to import this `limiter`; that is left as a
# low-priority cleanup and intentionally NOT done here to avoid changing startup
# behavior. If moving to multiple workers, back the limiter with a shared store
# (e.g. Redis via storage_uri) so counters are consistent across processes.
limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    debug=settings.DEBUG,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Explicit origins from env (comma-separated)
origins = [origin.strip() for origin in settings.FRONTEND_URL.split(",") if origin.strip()]

# Allow all ngrok public URLs automatically in non-production environments only.
# This avoids having to update config every time ngrok generates a new URL during development,
# but must not be enabled in production as it would allow any ngrok tunnel to bypass CORS.
NGROK_ORIGIN_REGEX = r"https?://[a-zA-Z0-9\-]+\.ngrok(-free)?\.(app|io|dev)"

cors_origin_regex = None
if settings.ENVIRONMENT != "production":
    cors_origin_regex = NGROK_ORIGIN_REGEX

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
    max_age=600,
)


# ── Global exception handler (ensures CORS headers survive 500s) ─────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):  # noqa: F841
    logger.error(f"Unhandled exception on {request.method} {request.url.path}:\n{traceback.format_exc()}")
    origin = request.headers.get("origin", "")
    headers = {}
    origin_allowed = origin in origins or (cors_origin_regex is not None and bool(re.match(cors_origin_regex, origin)))
    if origin_allowed:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "An unexpected error occurred. Check server logs."},
        headers=headers,
    )


# ── Security headers middleware ───────────────────────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    return response


# ── Audit context middleware ──────────────────────────────────────────────────
@app.middleware("http")
async def audit_context_middleware(request: Request, call_next):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    set_audit_context(ip_address, user_agent)
    response = await call_next(request)
    return response


@app.on_event("startup")
def on_startup():
    root_logger = logging.getLogger()
    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    logger.info(f"[App] Starting {settings.PROJECT_NAME} v{settings.PROJECT_VERSION} (Environment: {settings.ENVIRONMENT})")
    logger.info(f"[CORS] Explicit origins: {origins}")
    if cors_origin_regex:
        logger.info(f"[CORS] Also allowing all ngrok origins matching: {cors_origin_regex}")

    # Production safety assertions
    if settings.ENVIRONMENT == "production":
        assert not settings.DEBUG, "DEBUG must be False in production"
        assert len(settings.SECRET_KEY) >= 64, "SECRET_KEY must be at least 64 chars in production"
        for origin in origins:
            if 'localhost' in origin or '127.0.0.1' in origin:
                logger.warning(f"[Security] Production CORS allows local origin: {origin}")


    # Redis connectivity check
    logger.info("[Redis] Checking connection to Redis...")
    from app.core.redis import check_redis_connectivity
    if not check_redis_connectivity():
        if settings.ENVIRONMENT == "production":
            logger.critical("[Redis] Connection failed! Redis is required in production.")
            raise RuntimeError("Redis connection failed! Startup aborted.")
        else:
            logger.warning("[Redis] Connection failed! Caching will be disabled/degraded.")
    else:
        logger.info("[Redis] Connection established successfully!")

    logger.info("[Database] Connecting to database...")
    max_retries = 5
    retry_delay = 2
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("[Database] Connection established successfully!")
            break
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"[Database] Connection failed after {max_retries} attempts: {e}")
                raise e
            logger.warning(f"[Database] Attempt {attempt}/{max_retries} failed, retrying in {retry_delay}s...")
            time.sleep(retry_delay)

    # NOTE: Running migrations on boot is acceptable for this single-server
    # deployment. In a multi-worker / multi-instance setup this should be moved
    # to an explicit deploy step (run `alembic upgrade head` once before starting
    # workers) to avoid concurrent workers racing to apply the same migrations.
    logger.info("[Database] Running Alembic migrations...")
    from alembic.config import Config
    from alembic import command
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("disable_file_config", "true")
    command.upgrade(alembic_cfg, "head")
    logger.info("[Database] Migrations complete.")



    logger.info("[Database] Running startup seeding...")
    from app.database.session import SessionLocal
    from app.database.seed import (
        seed_default_admin,
        seed_scope_of_work,
        seed_leave_types,
        seed_attendance_rule,
        seed_calendar_settings,
        seed_calendar_permissions,
        seed_task_template_permissions,
        seed_idle_reasons,
    )
    db = SessionLocal()
    try:
        seed_default_admin(db)
        seed_scope_of_work(db)
        seed_leave_types(db)
        seed_attendance_rule(db)
        seed_calendar_settings(db)
        seed_calendar_permissions(db)
        seed_task_template_permissions(db)
        seed_idle_reasons(db)
        # Authorization Platform — seed Module & Feature registry
        from app.core.seeder import run_authorization_seeder
        run_authorization_seeder(db)
        # Auto-sync leave balances on boot
        try:
            from app.database.recompute_leave_balances import sync_all_leave_balances
            sync_all_leave_balances()
        except Exception as lbe:
            logger.warning(f"[Database] Leave balance sync warning: {lbe}")
        logger.info("[Database] Startup seeding completed successfully.")
    except Exception as e:
        logger.error(f"[Database] Seeding failed: {e}")
        raise e
    finally:
        db.close()

    # Clean up expired revoked tokens
    from app.models.revoked_token import RevokedToken
    from datetime import datetime, timezone
    from sqlalchemy import delete as sql_delete
    cleanup_db = SessionLocal()
    try:
        cleanup_db.execute(
            sql_delete(RevokedToken).where(RevokedToken.expires_at < datetime.now(timezone.utc))
        )
        cleanup_db.commit()
        logger.info("[Database] Cleaned up expired revoked tokens.")
    except Exception as ce:
        logger.warning(f"[Database] Revoked token cleanup failed (non-fatal): {ce}")
    finally:
        cleanup_db.close()

    # Initialize & Start Biometric Automated Sync Scheduler
    try:
        from app.services.biometric.scheduler_service import get_biometric_scheduler
        from app.models.biometric.bm_sync_config import BmSyncConfig
        from sqlalchemy import select
        scheduler = get_biometric_scheduler()
        scheduler.start()

        sched_db = SessionLocal()
        try:
            active_configs = list(sched_db.scalars(
                select(BmSyncConfig).where(BmSyncConfig.is_auto_sync == True, BmSyncConfig.is_active == True)
            ).all())
            for cfg in active_configs:
                scheduler.schedule_device(cfg.device_id, cfg.sync_interval_minutes or 1)
            logger.info(f"[BiometricScheduler] Auto-scheduled {len(active_configs)} biometric device(s).")
        finally:
            sched_db.close()
    except Exception as se:
        logger.warning(f"[BiometricScheduler] Startup init warning: {se}")


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api/v1")
app.include_router(role_router, prefix="/api/v1")
app.include_router(department_router, prefix="/api/v1")
app.include_router(designation_router, prefix="/api/v1")
app.include_router(employee_router, prefix="/api/v1")
app.include_router(team_router, prefix="/api/v1")
app.include_router(organization_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(client_router, prefix="/api/v1")
app.include_router(scope_of_work_router, prefix="/api/v1")
app.include_router(project_router, prefix="/api/v1")
app.include_router(task_router, prefix="/api/v1")
app.include_router(part_router, prefix="/api/v1")
app.include_router(attendance_router, prefix="/api/v1")
app.include_router(time_entry_router, prefix="/api/v1")
app.include_router(leave_router, prefix="/api/v1")
app.include_router(approval_router, prefix="/api/v1")
app.include_router(planning_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(work_session_router, prefix="/api/v1")
app.include_router(employee_break_router, prefix="/api/v1")
app.include_router(task_rework_router, prefix="/api/v1")
app.include_router(holiday_router, prefix="/api/v1")
app.include_router(calendar_settings_router, prefix="/api/v1")
app.include_router(email_configuration_router, prefix="/api/v1")
app.include_router(company_event_router, prefix="/api/v1")
app.include_router(calendar_router, prefix="/api/v1")
app.include_router(dashboard_widget_router, prefix="/api/v1")
app.include_router(task_template_router, prefix="/api/v1")
app.include_router(productivity_router, prefix="/api/v1")
app.include_router(dashboard_analytics_router, prefix="/api/v1")
app.include_router(schedule_review_router, prefix="/api/v1")
app.include_router(modules_router, prefix="/api/v1")
app.include_router(ticket_router, prefix="/api/v1")

# ── Biometric Module (isolated, additive) ─────────────────────────────────────
from app.routers.biometric.adms import router as adms_push_root_router
app.include_router(biometric_router, prefix="/api/v1")
app.include_router(adms_push_root_router)


@app.get("/", tags=["General"])
async def root() -> dict[str, str]:
    return {"message": "Cognitive ERP API Running"}


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


