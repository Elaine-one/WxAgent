from apscheduler.schedulers.background import BackgroundScheduler


def create_scheduler():
    try:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        jobstore = SQLAlchemyJobStore(url='sqlite:///workspace/data/scheduler.db')
        return BackgroundScheduler(jobstores={'default': jobstore})
    except Exception:
        return BackgroundScheduler()
