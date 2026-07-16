from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import get_current_user
from app.models import User
from app.snmp_client import get_printer_toner
from app.credentials import device_credentials

router = APIRouter(prefix="/api/printers", tags=["printers"])

@router.get("/")
def list_printers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    printers = db.query(models.Device).filter(models.Device.device_type == 'printer').all()
    result = []
    for p in printers:
        credentials = device_credentials(p)
        toner = get_printer_toner(p.ip, credentials["community"], p.snmp_version,
                                  credentials["snmp_user"], credentials["snmp_auth"], credentials["snmp_priv"])
        result.append({
            "id": p.id,
            "name": p.hostname or p.ip,
            "ip": p.ip,
            "model": p.model,
            "toner": toner,
            "status": p.status,
            "error": ""  # можно добавить позже
        })
    return result
