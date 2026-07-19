from copy import deepcopy
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app import crud, models
from app.auth import get_current_user, require_roles
from app.models import User
from app.schemas import DeviceUpdate, PortUpdate
from app.credentials import device_credentials, protect_device_credentials
from app.config import ip_is_allowed

router = APIRouter(prefix="/api/devices", tags=["devices"])

def _device_summary(device: models.Device) -> dict:
    return {
        "id": device.id,
        "ip": device.ip,
        "hostname": device.hostname,
        "type": device.device_type,
        "model": device.model,
        "status": device.status,
        "last_seen": device.last_seen.isoformat() if device.last_seen else None,
    }


@router.get("/")
def list_devices(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"items": [_device_summary(device) for device in crud.get_all_devices(db)]}

@router.get("")
async def get_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    devices = crud.get_all_devices(db)
    return {"items": [_device_summary(device) for device in devices]}


@router.get("/{device_id}")
def get_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = crud.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return _device_summary(device)


@router.patch("/{device_id}")
def update_device(
    device_id: int,
    data: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator")),
):
    device = crud.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    changes = protect_device_credentials(data.model_dump(exclude_unset=True))
    new_ip = changes.get("ip")
    if new_ip and not ip_is_allowed(new_ip):
        raise HTTPException(status_code=403, detail="Device is outside ALLOWED_NETWORKS")
    if new_ip and db.query(models.Device).filter(
        models.Device.ip == new_ip,
        models.Device.id != device_id,
    ).first():
        raise HTTPException(status_code=400, detail="Device with this IP already exists")
    for field, value in changes.items():
        setattr(device, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Device with this IP already exists") from exc
    db.refresh(device)
    crud.add_audit_event(db, current_user.username, "device_updated", f"{device.id}: {device.ip}")
    return _device_summary(device)


@router.delete("/{device_id}")
def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    device = crud.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    label = f"{device.id}: {device.hostname or device.ip}"
    db.query(models.DeviceEvent).filter(models.DeviceEvent.device_id == device_id).delete(
        synchronize_session=False
    )
    db.query(models.DeviceAvailability).filter(
        models.DeviceAvailability.device_id == device_id
    ).delete(synchronize_session=False)
    db.delete(device)
    db.commit()
    crud.add_audit_event(db, current_user.username, "device_deleted", label)
    return {"status": "deleted"}

@router.get("/{device_id}/ports")
async def get_ports(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    device = crud.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not ip_is_allowed(device.ip):
        raise HTTPException(status_code=403, detail="Device is outside ALLOWED_NETWORKS")
    return device.ports or []


@router.post("/{device_id}/ports/refresh")
async def refresh_ports(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator")),
):
    device = crud.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not ip_is_allowed(device.ip):
        raise HTTPException(status_code=403, detail="Device is outside ALLOWED_NETWORKS")
    if device.device_type != "switch":
        raise HTTPException(status_code=400, detail="Port polling is available only for switches")

    from app.snmp_client import get_switch_port_snapshot
    credentials = device_credentials(device)
    ports = get_switch_port_snapshot(
        device.ip, credentials["community"], device.snmp_version,
        credentials["snmp_user"], credentials["snmp_auth"], credentials["snmp_priv"],
    )
    if not ports:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SNMP port polling returned no data; cached ports were preserved",
        )
    crud.update_device_ports(db, device_id, ports)
    crud.add_audit_event(db, current_user.username, "device_ports_refreshed", str(device_id))
    return {"items": ports, "count": len(ports)}

@router.put("/{device_id}/ports/{port}")
async def update_port(
    device_id: int,
    port: Annotated[int, Path(ge=1)],
    update_data: PortUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator"))
):
    device = crud.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    # Assign a fresh JSON value so SQLAlchemy reliably detects the mutation.
    ports = deepcopy(device.ports or [])
    for p in ports:
        if p.get("port") == port:
            changes = update_data.model_dump(exclude_none=True)
            if "description" in changes:
                p["description_override"] = changes["description"]
            if "mode" in changes:
                p["mode_override"] = changes["mode"]
            p.update(changes)
            break
    else:
        raise HTTPException(status_code=404, detail="Port not found")
    device.ports = ports
    db.commit()
    crud.add_audit_event(db, current_user.username, "device_port_updated", f"{device_id}/{port}")
    return {"status": "ok"}
