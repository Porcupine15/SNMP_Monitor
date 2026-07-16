import ipaddress
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth import require_roles
from app.credentials import protect_device_credentials
from app.models import User
from app.snmp_client import get_device_info, ping_device

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/discovery", tags=["discovery"])


class DiscoveryRequest(BaseModel):
    network: str
    community: str = "public"
    snmp_version: str = "v2c"


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

    discovered, added = [], []
    for ip in network.hosts():
        ip_str = str(ip)
        if not ping_device(ip_str, timeout=1):
            continue
        info = get_device_info(ip_str, request.community, request.snmp_version)
        if not info or db.query(models.Device).filter(models.Device.ip == ip_str).first():
            continue
        model = info.get("model", "")
        device_type = "printer" if "printer" in model.lower() else "router" if "router" in model.lower() else "switch"
        db.add(models.Device(**protect_device_credentials({"ip": ip_str, "hostname": info.get("hostname", ""), "model": model, "device_type": device_type, "snmp_version": request.snmp_version, "community": request.community, "status": "online", "last_seen": None})))
        added.append(ip_str)
        discovered.append({"ip": ip_str, "hostname": info.get("hostname", ""), "model": model, "status": "online"})
    db.commit()
    return {"discovered": len(discovered), "added": len(added), "devices": discovered}
