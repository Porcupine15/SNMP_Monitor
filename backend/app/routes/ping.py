from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from ipaddress import ip_address
from sqlalchemy.orm import Session
from app import crud
from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.scheduler import get_monitoring_settings

router = APIRouter(prefix="/api/ping", tags=["ping"])

class PingRequest(BaseModel):
    ip: str
    count: int | None = Field(default=None, ge=1, le=10)
    timeout: int | None = Field(default=None, ge=1, le=10)

    @field_validator("ip")
    def validate_ip(cls, value: str) -> str:
        return str(ip_address(value))

@router.post("")
def ping(request: PingRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from icmplib import ping
    settings = get_monitoring_settings(db)
    count = request.count or settings["ping_count"]
    timeout = request.timeout or settings["ping_timeout_seconds"]
    try:
        result = ping(request.ip, count=count, timeout=timeout)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ping failed: {exc}") from exc
    crud.add_audit_event(db, current_user.username, "ping", request.ip)
    return {
        "ip": request.ip,
        "alive": result.is_alive,
        "packets_sent": result.packets_sent,
        "packets_received": result.packets_received,
        "packet_loss": result.packet_loss,
        "avg_rtt": result.avg_rtt,
        "output": f"{request.ip}: {'доступен' if result.is_alive else 'недоступен'}, потери {result.packet_loss}%, средняя задержка {result.avg_rtt} ms"
    }
