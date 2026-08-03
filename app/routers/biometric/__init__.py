from fastapi import APIRouter
from app.routers.biometric.devices import router as devices_router
from app.routers.biometric.connection_profiles import router as connection_profiles_router
from app.routers.biometric.employee_mapping import router as employee_mapping_router
from app.routers.biometric.sync import router as sync_router
from app.routers.biometric.logs import router as logs_router
from app.routers.biometric.live import router as live_router
from app.routers.biometric.health import router as health_router
from app.routers.biometric.connection_test import router as connection_test_router
from app.routers.biometric.adms import router as adms_router

router = APIRouter(prefix="/biometric", tags=["Biometric"])
router.include_router(devices_router)
router.include_router(connection_profiles_router)
router.include_router(employee_mapping_router)
router.include_router(sync_router)
router.include_router(logs_router)
router.include_router(live_router)
router.include_router(health_router)
router.include_router(connection_test_router)
router.include_router(adms_router)
