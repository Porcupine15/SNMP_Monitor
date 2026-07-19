from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app import crud, models
from app.schemas import DeviceCreate, DeviceOut, UserAdminCreate, UserRoleUpdate, UserStatusUpdate, UserOut
from app.auth import get_password_hash, require_roles
from app.config import ip_is_allowed
from app.models import User

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin"))):
    return db.query(User).order_by(User.username).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserAdminCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    conditions = [User.username == data.username]
    if data.email:
        conditions.append(User.email == data.email)
    if db.query(User).filter(or_(*conditions)).first():
        raise HTTPException(status_code=400, detail="Username or email already registered")
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=get_password_hash(data.password),
        role=data.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username or email already registered") from exc
    db.refresh(user)
    crud.add_audit_event(db, current_user.username, "user_created", f"{user.username}: {user.role}")
    return user

@router.put("/users/{user_id}/role", response_model=UserOut)
def update_user_role(user_id: int, data: UserRoleUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin"))):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == current_user.id:
        raise HTTPException(400, "Cannot change own role")
    user.role = data.role
    db.commit()
    db.refresh(user)
    crud.add_audit_event(db, current_user.username, "user_role_updated", f"{user.username}: {user.role}")
    return user


@router.put("/users/{user_id}/status", response_model=UserOut)
def update_user_status(
    user_id: int,
    data: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == current_user.id and not data.is_active:
        raise HTTPException(400, "Cannot deactivate own account")
    user.is_active = data.is_active
    db.commit()
    db.refresh(user)
    crud.add_audit_event(
        db,
        current_user.username,
        "user_status_updated",
        f"{user.username}: {'active' if user.is_active else 'inactive'}",
    )
    return user

@router.post("/devices")
def add_device(
    device: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator"))
):
    if not ip_is_allowed(device.ip):
        raise HTTPException(status_code=403, detail="Device is outside ALLOWED_NETWORKS")
    existing = db.query(models.Device).filter(models.Device.ip == device.ip).first()
    if existing:
        raise HTTPException(status_code=400, detail="Device with this IP already exists")
    new_device = crud.create_device(db, device.model_dump())
    crud.add_audit_event(db, current_user.username, "device_created", f"{new_device.id}: {new_device.ip}")
    return {"status": "created", "id": new_device.id}

@router.get("/devices", response_model=list[DeviceOut])
def list_all_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator"))
):
    return crud.get_all_devices(db)
