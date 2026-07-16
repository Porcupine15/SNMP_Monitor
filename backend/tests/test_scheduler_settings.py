from types import SimpleNamespace

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.routes import operations
from app import scheduler as scheduler_module


def _database_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_monitoring_settings_ignore_unknown_and_recover_invalid_values():
    db = _database_session()
    try:
        db.add_all(
            [
                models.AppSetting(key="poll_interval_seconds", value="invalid"),
                models.AppSetting(key="ping_count", value="99"),
                models.AppSetting(key="unrelated_text_setting", value="enabled"),
            ]
        )
        db.commit()

        assert scheduler_module.get_monitoring_settings(db) == {
            "poll_interval_seconds": 60,
            "ping_count": 10,
            "ping_timeout_seconds": 2,
        }
    finally:
        db.close()


def test_polling_job_is_created_and_rescheduled_with_new_interval():
    test_scheduler = BackgroundScheduler()

    scheduler_module.reschedule_device_polling(75, scheduler_instance=test_scheduler)
    job = test_scheduler.get_job(scheduler_module.POLL_JOB_ID)
    assert job.trigger.interval.total_seconds() == 75

    scheduler_module.reschedule_device_polling(180, scheduler_instance=test_scheduler)
    job = test_scheduler.get_job(scheduler_module.POLL_JOB_ID)
    assert job.trigger.interval.total_seconds() == 180


def test_scheduler_start_uses_interval_stored_in_database(monkeypatch):
    db = _database_session()
    db.add(models.AppSetting(key="poll_interval_seconds", value="150"))
    db.commit()
    test_scheduler = BackgroundScheduler()
    monkeypatch.setattr(scheduler_module, "scheduler", test_scheduler)
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: db)

    try:
        scheduler_module.start_scheduler()
        job = test_scheduler.get_job(scheduler_module.POLL_JOB_ID)
        assert job.trigger.interval.total_seconds() == 150
        assert test_scheduler.running
    finally:
        scheduler_module.shutdown_scheduler()


def test_updating_settings_reschedules_active_polling_job(monkeypatch):
    db = _database_session()
    applied_intervals = []
    monkeypatch.setattr(
        operations,
        "reschedule_device_polling",
        lambda interval: applied_intervals.append(interval),
    )

    try:
        result = operations.update_settings(
            operations.SettingsUpdate(
                poll_interval_seconds=120,
                ping_count=4,
                ping_timeout_seconds=3,
            ),
            db=db,
            current_user=SimpleNamespace(username="admin"),
        )

        assert applied_intervals == [120]
        assert result == {
            "poll_interval_seconds": 120,
            "ping_count": 4,
            "ping_timeout_seconds": 3,
        }
        audit = db.query(models.AuditEvent).one()
        assert audit.action == "settings_updated"
    finally:
        db.close()
