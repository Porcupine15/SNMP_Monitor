from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import get_current_user
from app.models import User

router = APIRouter(prefix="/api/printers", tags=["printers"])

@router.get("/")
def list_printers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    printers = db.query(models.Device).filter(models.Device.device_type == 'printer').all()
    result = []
    for p in printers:
        result.append({
            "id": p.id,
            "name": p.hostname or p.ip,
            "ip": p.ip,
            "model": p.model,
            "toner": p.toner,
            "status": p.status,
            "error": ""  # можно добавить позже
        })
    return result
