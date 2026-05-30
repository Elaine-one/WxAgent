from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from config import WORKSPACE_DIR


def create_scheduler():
    db_dir = WORKSPACE_DIR / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "scheduler.db"
    try:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        jobstore = SQLAlchemyJobStore(url=f'sqlite:///{db_path}')
        return BackgroundScheduler(jobstores={'default': jobstore})
    except Exception:
        return BackgroundScheduler()
