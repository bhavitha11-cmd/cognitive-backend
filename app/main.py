import logging
import time
import traceback
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
from app.routers.project import router as project_router
from app.routers.task import router as task_router
from app.routers.attendance import router as attendance_router
from app.routers.time_entry import router as time_entry_router
from app.routers.leave import router as leave_router
from app.routers.planning import router as planning_router
from app.routers.analytics import router as analytics_router
from app.middleware.audit_context import set_audit_context
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title=settings.PROJECT_NAME, version=settings.PROJECT_VERSION, debug=settings.DEBUG)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ─────────────────────────────────────────────────────────────────────
origins = [origin.strip() for origin in settings.FRONTEND_URL.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With"],
    expose_headers=["X-Total-Count"],
    max_age=600,
)


# ── Global exception handler (ensures CORS headers survive 500s) ─────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):  # noqa: F841
    logger.error(f"Unhandled exception on {request.method} {request.url.path}:\n{traceback.format_exc()}")
    origin = request.headers.get("origin", "")
    headers = {}
    if origin in origins:
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
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── Audit context middleware ──────────────────────────────────────────────────
@app.middleware("http")
async def audit_context_middleware(request: Request, call_next):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    set_audit_context(ip_address, user_agent)
    response = await call_next(request)
    return response


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    logger.info(f"[App] Starting {settings.PROJECT_NAME} v{settings.PROJECT_VERSION} (Environment: {settings.ENVIRONMENT})")
    logger.info(f"[CORS] Allowed Frontend CORS Origins: {origins}")

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

    logger.info("[Database] Creating tables if not exist...")
    import app.models  # noqa: F401 — side-effect import registers all models with Base.metadata
    from app.database.base import Base
    Base.metadata.create_all(bind=engine)
    logger.info("[Database] Tables ready.")

    logger.info("[Database] Running startup seeding...")
    from app.database.session import SessionLocal
    from app.database.seed import seed_default_admin, seed_scope_of_work, seed_leave_types, seed_attendance_rule
    db = SessionLocal()
    try:
        seed_default_admin(db)
        seed_scope_of_work(db)
        seed_leave_types(db)
        seed_attendance_rule(db)
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
app.include_router(attendance_router, prefix="/api/v1")
app.include_router(time_entry_router, prefix="/api/v1")
app.include_router(leave_router, prefix="/api/v1")
app.include_router(planning_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")


@app.get("/", tags=["General"])
async def root() -> dict[str, str]:
    return {"message": "Cognitive ERP API Running"}


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/db-check")
def db_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"database": "connected"}
    except Exception as e:
        return {"database": "failed", "error": str(e)}
