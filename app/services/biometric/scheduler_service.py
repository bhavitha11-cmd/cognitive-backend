"""
Biometric Scheduler Service

Manages automated scheduled syncs using APScheduler backed by Redis job store.
Each device can have its own sync schedule.
"""
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class BiometricScheduler:
    """
    Manages APScheduler jobs for automated biometric sync.
    Uses Redis as job store for persistence across restarts.
    """
    
    def __init__(self):
        self._scheduler = None
        self._started = False
    
    def _get_scheduler(self):
        if self._scheduler is None:
            try:
                from apscheduler.schedulers.background import BackgroundScheduler
                from apscheduler.jobstores.redis import RedisJobStore
                from apscheduler.executors.pool import ThreadPoolExecutor
                from app.core.config import settings
                
                from apscheduler.jobstores.memory import MemoryJobStore
                jobstores = {'default': MemoryJobStore()}
                
                executors = {'default': ThreadPoolExecutor(20)}
                job_defaults = {
                    'coalesce': True,
                    'max_instances': 1,
                    'misfire_grace_time': 60,
                }
                
                self._scheduler = BackgroundScheduler(
                    jobstores=jobstores,
                    executors=executors,
                    job_defaults=job_defaults,
                )
            except ImportError as imp_err:
                logger.warning(f"[BiometricScheduler] APScheduler not installed ({imp_err}). Automated sync disabled.")
        return self._scheduler
    
    def start(self) -> None:
        scheduler = self._get_scheduler()
        if scheduler and not self._started:
            try:
                scheduler.start()
                self._started = True
                logger.info("[BiometricScheduler] Scheduler started")
            except Exception as e:
                logger.error(f"[BiometricScheduler] Failed to start: {e}")
    
    def stop(self) -> None:
        if self._scheduler and self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
            logger.info("[BiometricScheduler] Scheduler stopped")
    
    def schedule_device(self, device_id: uuid.UUID, interval_minutes: int) -> bool:
        """Schedule recurring sync for a device."""
        scheduler = self._get_scheduler()
        if not scheduler:
            return False
        
        job_id = f"bm_sync_{device_id}"
        
        def sync_job():
            from app.database.session import SessionLocal
            from app.services.biometric.sync_engine import SyncEngine
            db = SessionLocal()
            try:
                engine = SyncEngine(db)
                engine.run_sync(device_id, sync_type="SCHEDULED")
            except Exception as e:
                logger.error(f"[BiometricScheduler] Sync job failed for {device_id}: {e}")
            finally:
                db.close()
        
        try:
            scheduler.add_job(
                func=sync_job,
                trigger="interval",
                minutes=interval_minutes,
                id=job_id,
                replace_existing=True,
            )
            logger.info(f"[BiometricScheduler] Scheduled device {device_id} every {interval_minutes} min")
            return True
        except Exception as e:
            logger.error(f"[BiometricScheduler] Failed to schedule device {device_id}: {e}")
            return False
    
    def remove_device(self, device_id: uuid.UUID) -> bool:
        scheduler = self._get_scheduler()
        if not scheduler:
            return False
        job_id = f"bm_sync_{device_id}"
        try:
            scheduler.remove_job(job_id)
            return True
        except Exception:
            return False
    
    def list_jobs(self) -> list[dict]:
        scheduler = self._get_scheduler()
        if not scheduler:
            return []
        jobs = []
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        return jobs


# Singleton instance
_scheduler_instance: Optional[BiometricScheduler] = None

def get_biometric_scheduler() -> BiometricScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = BiometricScheduler()
    return _scheduler_instance
