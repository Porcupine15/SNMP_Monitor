from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import get_current_user
from app.models import User
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/stats")
def get_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    total = db.query(models.Device).count()
    online = db.query(models.Device).filter(models.Device.status == 'online').count()
    offline = total - online
    clients = db.query(models.NetworkClient).count()
    active_clients = db.query(models.NetworkClient).filter(
        models.NetworkClient.last_seen >= datetime.now(timezone.utc) - timedelta(minutes=10)
    ).count()
    return {"total": total, "online": online, "offline": offline, "alerts": 0,
            "clients": clients, "active_clients": active_clients}

@router.get("/events")
def get_events(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    events = (
        db.query(models.DeviceEvent)
        .order_by(models.DeviceEvent.created_at.desc())
        .limit(30)
        .all()
    )
    return [
        {
            "id": event.id,
            "device_id": event.device_id,
            "type": event.event_type,
            "msg": event.message,
            "time": event.created_at.isoformat() if event.created_at else None,
        }
        for event in events
    ]
