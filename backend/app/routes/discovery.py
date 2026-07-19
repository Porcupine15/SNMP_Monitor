import ipaddress
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud, models
from app.auth import require_roles
from app.credentials import protect_device_credentials
from app.config import network_is_allowed
from app.models import User
from app.scan_control import active_network_scan
from app.snmp_client import get_device_info, ping_device

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/discovery", tags=["discovery"])


class DiscoveryRequest(BaseModel):
    network: str
    community: str = Field(..., min_length=1, max_length=255)
    snmp_version: Literal["v1", "v2c"] = "v2c"


@router.post("/scan")
def scan_network(
    request: DiscoveryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator")),
):
    try:
        network = ipaddress.ip_network(request.network, strict=False)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid network CIDR")
    if network.num_addresses > 1024:
        raise HTTPException(status_code=400, detail="Для безопасности за один запуск можно сканировать не более 1024 адресов")
    if not network_is_allowed(str(network)):
        raise HTTPException(status_code=403, detail="Network is outside ALLOWED_NETWORKS")

    if not active_network_scan.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Another network scan is already running")
    try:
        discovered, added = [], []
        for ip in network.hosts():
            ip_str = str(ip)
            if not ping_device(ip_str, timeout=1):
                continue
            info = get_device_info(ip_str, request.community, request.snmp_version)
            if not info or db.query(models.Device).filter(models.Device.ip == ip_str).first():
                continue
            hostname = str(info.get("hostname", ""))[:100]
            model = str(info.get("model", ""))[:100]
            device_type = "printer" if "printer" in model.lower() else "router" if "router" in model.lower() else "switch"
            db.add(models.Device(**protect_device_credentials({"ip": ip_str, "hostname": hostname, "model": model, "device_type": device_type, "snmp_version": request.snmp_version, "community": request.community, "status": "online", "last_seen": None})))
            added.append(ip_str)
            discovered.append({"ip": ip_str, "hostname": hostname, "model": model, "status": "online"})
        db.commit()
        crud.add_audit_event(
            db,
            current_user.username,
            "snmp_discovery_completed",
            f"{network}: {len(added)} device(s) added",
        )
        return {"discovered": len(discovered), "added": len(added), "devices": discovered}
    finally:
        active_network_scan.release()
