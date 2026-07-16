from sqlalchemy.orm import Session
from datetime import datetime
from app import models
from app.credentials import protect_device_credentials
from app.notifications import send_status_notification

def get_all_devices(db: Session):
    return db.query(models.Device).all()

def get_device(db: Session, device_id: int):
    return db.query(models.Device).filter(models.Device.id == device_id).first()

def create_device(db: Session, device_data: dict):
    db_device = models.Device(**protect_device_credentials(device_data))
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    return db_device

def update_device_ports(db: Session, device_id: int, ports: list):
    device = get_device(db, device_id)
    if device:
        # Keep locally entered labels when the next SNMP poll replaces telemetry.
        previous_ports = {port.get("port"): port for port in (device.ports or [])}
        for port in ports:
            previous = previous_ports.get(port.get("port"), {})
            if previous.get("description_override") is not None:
                port["description_override"] = previous["description_override"]
                port["description"] = previous["description_override"]
            if previous.get("mode_override") is not None:
                port["mode_override"] = previous["mode_override"]
                port["mode"] = previous["mode_override"]
        device.ports = ports
        device.last_seen = datetime.utcnow()
        db.commit()
        db.refresh(device)
    return device

def update_device_status(db: Session, device_id: int, status: str):
    device = get_device(db, device_id)
    if device:
        previous_status = device.status
        device.status = status
        device.last_seen = datetime.utcnow()
        db.add(models.DeviceAvailability(device_id=device.id, status=status))
        if previous_status != status:
            db.add(models.DeviceEvent(
                device_id=device.id,
                event_type="status_changed",
                message=f"{device.hostname or device.ip}: {previous_status} → {status}",
            ))
        db.commit()
        if previous_status != status:
            send_status_notification(f"SNMP Monitor: {device.hostname or device.ip}: {previous_status} → {status}")
        db.refresh(device)
    return device


def add_audit_event(db: Session, username: str, action: str, details: str = ""):
    db.add(models.AuditEvent(username=username, action=action, details=details))
    db.commit()
