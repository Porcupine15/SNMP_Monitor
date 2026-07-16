import ipaddress
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.client_discovery import scan
from app.database import get_db
from app.models import NetworkClient, User
from app.schemas import AgentSync, NetworkScanRequest


router = APIRouter(prefix="/api/clients", tags=["clients"])


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _client_for_observation(db: Session, ip: str, mac: str | None) -> NetworkClient:
    """Resolve a current client by stable MAC first, then by its leased IP."""
    by_ip = db.query(NetworkClient).filter_by(ip=ip).first()
    by_mac = db.query(NetworkClient).filter_by(mac=mac).first() if mac else None

    if by_mac and by_ip and by_mac.id != by_ip.id:
        # DHCP moved a known client onto an address occupied by an old record.
        # The table represents current identities, so merge the stale duplicate.
        if by_ip.first_seen and (
            not by_mac.first_seen
            or _aware_utc(by_ip.first_seen) < _aware_utc(by_mac.first_seen)
        ):
            by_mac.first_seen = by_ip.first_seen
        db.delete(by_ip)
        db.flush()
        by_ip = None

    row = by_mac or by_ip
    if row is None:
        row = NetworkClient(ip=ip)
        db.add(row)
    elif row.ip != ip:
        row.ip = ip
    return row


@router.post("/agent-sync")
def agent_sync(
    data: AgentSync,
    x_lan_agent_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    expected = os.getenv("LAN_AGENT_TOKEN", "")
    if not expected or not secrets.compare_digest(x_lan_agent_token, expected):
        raise HTTPException(status_code=401, detail="Invalid LAN agent token")
    seen_at = datetime.now(timezone.utc)
    for item in data.clients:
        row = _client_for_observation(db, item.ip, item.mac)
        if item.mac:
            row.mac = item.mac
        if item.hostname:
            row.hostname = item.hostname
        row.status = "online"
        row.last_seen = seen_at
    db.commit()
    return {"received": len(data.clients)}


@router.get("")
def clients(
    query: str = Query(default="", max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.query(NetworkClient).order_by(NetworkClient.last_seen.desc()).all()
    normalized_query = query.strip().lower()
    rows = [
        row
        for row in rows
        if not normalized_query
        or normalized_query in row.ip.lower()
        or normalized_query in (row.mac or "").lower()
        or normalized_query in (row.hostname or "").lower()
        or normalized_query in (row.vendor or "").lower()
    ]
    stale_before = datetime.now(timezone.utc) - timedelta(minutes=10)
    return {
        "items": [
            {
                "id": row.id,
                "ip": row.ip,
                "mac": row.mac,
                "hostname": row.hostname,
                "vendor": row.vendor,
                "status": (
                    "offline"
                    if row.last_seen and _aware_utc(row.last_seen) < stale_before
                    else row.status
                ),
                "last_seen": row.last_seen.isoformat() if row.last_seen else None,
            }
            for row in rows
        ]
    }


@router.post("/scan")
def scan_clients(
    request: NetworkScanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    network = ipaddress.ip_network(request.network, strict=False)
    if network.num_addresses > 1024:
        raise HTTPException(status_code=400, detail="Maximum 1024 addresses")
    found = scan(str(network))
    for item in found:
        row = _client_for_observation(db, item["ip"], item["mac"])
        if item["mac"]:
            row.mac = item["mac"].lower()
        if item["hostname"]:
            row.hostname = item["hostname"]
        row.status = "online"
        row.last_seen = item["seen_at"]
    db.commit()
    return {"found": len(found), "items": found}
