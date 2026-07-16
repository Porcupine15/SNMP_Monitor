import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import crud, models
from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import User
from app.scheduler import (
    get_monitoring_settings,
    reschedule_device_polling,
)

router = APIRouter(prefix="/api/operations", tags=["operations"])


def _csv_value(value):
    """Prevent spreadsheet formula execution when exported text is opened."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


class SettingsUpdate(BaseModel):
    poll_interval_seconds: int = Field(60, ge=15, le=3600)
    ping_count: int = Field(3, ge=1, le=10)
    ping_timeout_seconds: int = Field(2, ge=1, le=10)


def settings_dict(db: Session) -> dict:
    return get_monitoring_settings(db)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return settings_dict(db)


@router.put("/settings")
def update_settings(data: SettingsUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin"))):
    values = data.model_dump()
    for key, value in values.items():
        row = db.get(models.AppSetting, key)
        if row:
            row.value = str(value)
        else:
            db.add(models.AppSetting(key=key, value=str(value)))
    db.commit()

    # Apply the new interval immediately; an application restart is not needed.
    reschedule_device_polling(data.poll_interval_seconds)
    crud.add_audit_event(db, current_user.username, "settings_updated", "monitoring settings")
    return settings_dict(db)


@router.get("/audit")
def audit(db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin"))):
    rows = db.query(models.AuditEvent).order_by(models.AuditEvent.created_at.desc()).limit(100).all()
    return [{"username": r.username, "action": r.action, "details": r.details, "time": r.created_at.isoformat()} for r in rows]


@router.get("/availability/{device_id}")
def availability(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not db.get(models.Device, device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    rows = db.query(models.DeviceAvailability).filter(models.DeviceAvailability.device_id == device_id).order_by(models.DeviceAvailability.checked_at.desc()).limit(200).all()
    return [{"status": row.status, "time": row.checked_at.isoformat()} for row in reversed(rows)]


@router.get("/export/{resource}")
def export(resource: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if resource == "devices":
        headers = ["id", "ip", "hostname", "model", "type", "status"]
        rows = [
            [d.id, d.ip, d.hostname, d.model, d.device_type, d.status]
            for d in db.query(models.Device).order_by(models.Device.id).all()
        ]
    elif resource == "events":
        headers = ["device_id", "type", "message", "time"]
        rows = [
            [e.device_id, e.event_type, e.message, e.created_at]
            for e in db.query(models.DeviceEvent).order_by(models.DeviceEvent.created_at).all()
        ]
    elif resource == "clients":
        headers = ["id", "ip", "mac", "hostname", "vendor", "status", "first_seen", "last_seen"]
        rows = [
            [
                client.id,
                client.ip,
                client.mac,
                client.hostname,
                client.vendor,
                client.status,
                client.first_seen,
                client.last_seen,
            ]
            for client in db.query(models.NetworkClient).order_by(models.NetworkClient.ip).all()
        ]
    elif resource == "availability":
        headers = ["id", "device_id", "status", "checked_at"]
        rows = [
            [row.id, row.device_id, row.status, row.checked_at]
            for row in db.query(models.DeviceAvailability)
            .order_by(models.DeviceAvailability.checked_at)
            .all()
        ]
    else:
        raise HTTPException(status_code=404, detail="Unknown export resource")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows([[_csv_value(value) for value in row] for row in rows])
    crud.add_audit_event(db, current_user.username, "csv_export", resource)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{resource}.csv"'},
    )
