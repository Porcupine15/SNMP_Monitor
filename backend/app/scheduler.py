import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app import crud, models
from app.credentials import device_credentials
from app.database import SessionLocal
from app.snmp_client import get_printer_toner, get_switch_port_snapshot, ping_device

logger = logging.getLogger(__name__)

POLL_JOB_ID = "device_polling"
MONITORING_SETTING_BOUNDS = {
    "poll_interval_seconds": (60, 15, 3600),
    "ping_count": (3, 1, 10),
    "ping_timeout_seconds": (2, 1, 10),
}


def _new_scheduler() -> BackgroundScheduler:
    return BackgroundScheduler()


scheduler = _new_scheduler()


def _normalise_setting(key: str, value: Any) -> int:
    default, minimum, maximum = MONITORING_SETTING_BOUNDS[key]
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        logger.warning("Invalid value for %s: %r; using %s", key, value, default)
        return default
    return max(minimum, min(parsed, maximum))


def get_monitoring_settings(db) -> dict[str, int]:
    """Return validated monitoring settings without leaking unrelated settings."""
    rows = (
        db.query(models.AppSetting)
        .filter(models.AppSetting.key.in_(MONITORING_SETTING_BOUNDS))
        .all()
    )
    stored = {row.key: row.value for row in rows}
    return {
        key: _normalise_setting(key, stored.get(key, bounds[0]))
        for key, bounds in MONITORING_SETTING_BOUNDS.items()
    }


def _poll_single_device(db, device, *, ping_timeout: int) -> None:
    online = ping_device(device.ip, timeout=float(ping_timeout))
    status = "online" if online else "offline"
    crud.update_device_status(db, device.id, status)

    if not online or device.device_type not in {"switch", "printer"}:
        return

    credentials = device_credentials(device)
    snmp_arguments = (
        device.ip,
        credentials["community"],
        device.snmp_version,
        credentials["snmp_user"],
        credentials["snmp_auth"],
        credentials["snmp_priv"],
    )

    if device.device_type == "switch":
        ports = get_switch_port_snapshot(*snmp_arguments)
        crud.update_device_ports(db, device.id, ports)
        return

    toner = get_printer_toner(*snmp_arguments)
    db_device = crud.get_device(db, device.id)
    if db_device:
        db_device.toner = toner
        db.commit()


def poll_devices() -> None:
    logger.info("Запуск фонового опроса устройств")
    db = SessionLocal()
    try:
        settings = get_monitoring_settings(db)
        devices = crud.get_all_devices(db)
        for device in devices:
            try:
                _poll_single_device(
                    db,
                    device,
                    ping_timeout=settings["ping_timeout_seconds"],
                )
            except Exception:
                # A failure on one host must not prevent polling the remaining hosts.
                db.rollback()
                logger.exception("Ошибка при опросе устройства %s", device.ip)
    except Exception:
        logger.exception("Не удалось выполнить фоновый опрос устройств")
    finally:
        db.close()


def reschedule_device_polling(
    interval_seconds: int,
    *,
    scheduler_instance: BackgroundScheduler | None = None,
) -> int:
    """Create or update the polling job and return the validated interval."""
    active_scheduler = scheduler if scheduler_instance is None else scheduler_instance
    interval = _normalise_setting("poll_interval_seconds", interval_seconds)
    trigger = IntervalTrigger(seconds=interval)

    if active_scheduler.get_job(POLL_JOB_ID) is None:
        active_scheduler.add_job(
            poll_devices,
            trigger=trigger,
            id=POLL_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    else:
        active_scheduler.reschedule_job(POLL_JOB_ID, trigger=trigger)

    logger.info("Интервал фонового опроса установлен: %s сек.", interval)
    return interval


def start_scheduler() -> None:
    if scheduler.running:
        return

    interval = MONITORING_SETTING_BOUNDS["poll_interval_seconds"][0]
    db = SessionLocal()
    try:
        interval = get_monitoring_settings(db)["poll_interval_seconds"]
    except Exception:
        logger.exception("Не удалось прочитать настройки планировщика; используется интервал по умолчанию")
    finally:
        db.close()

    reschedule_device_polling(interval)
    scheduler.start()
    logger.info("Планировщик запущен")


def shutdown_scheduler() -> None:
    global scheduler

    current_scheduler = scheduler
    if current_scheduler.running:
        current_scheduler.shutdown(wait=False)
        logger.info("Планировщик остановлен")

    # APScheduler executors cannot be safely reused after shutdown.  A fresh
    # instance also makes repeated FastAPI lifespan runs deterministic in tests.
    scheduler = _new_scheduler()
