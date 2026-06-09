import logging
from fastapi import FastAPI, Request
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
from app.middleware.audit_context import set_audit_context

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title=settings.PROJECT_NAME, version=settings.PROJECT_VERSION, debug=settings.DEBUG)

origins = [origin.strip() for origin in settings.FRONTEND_URL.split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def on_startup():
    logger.info(f"[App] Starting {settings.PROJECT_NAME} v{settings.PROJECT_VERSION} (Environment: {settings.ENVIRONMENT})")
    logger.info(f"[CORS] Allowed Frontend CORS Origins: {origins}")
    
    # 1. Verify database connectivity
    logger.info("[Database] Connecting to database...")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("[Database] Connection established successfully!")
    except Exception as e:
        logger.error(f"[Database] Connection failed: {e}")
        raise e
        
    # 2. Perform database seeding
    logger.info("[Database] Running startup seeding...")
    from app.database.session import SessionLocal
    from app.database.seed import seed_default_admin
    db = SessionLocal()
    try:
        seed_default_admin(db)
        logger.info("[Database] Startup seeding completed successfully.")
    except Exception as e:
        logger.error(f"[Database] Seeding failed: {e}")
        raise e
    finally:
        db.close()



@app.middleware("http")
async def audit_context_middleware(request: Request, call_next):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    set_audit_context(ip_address, user_agent)
    response = await call_next(request)
    return response

app.include_router(auth_router, prefix="/api/v1")
app.include_router(role_router, prefix="/api/v1")
app.include_router(department_router, prefix="/api/v1")
app.include_router(designation_router, prefix="/api/v1")
app.include_router(employee_router, prefix="/api/v1")
app.include_router(team_router, prefix="/api/v1")
app.include_router(organization_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")


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
