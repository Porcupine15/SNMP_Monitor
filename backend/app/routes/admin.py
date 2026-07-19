from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app import crud, models
from app.schemas import DeviceCreate, DeviceOut, UserAdminCreate, UserAdminUpdate, UserRoleUpdate, UserStatusUpdate, UserOut
from app.auth import get_password_hash, require_roles
from app.config import ip_is_allowed
from app.models import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _audit(db: Session, username: str, action: str, details: str) -> None:
    """Add an audit event to the same transaction as the user mutation."""
    db.add(models.AuditEvent(username=username, action=action, details=details))


def _lock_user_management_rows(db: Session, user_id: int) -> tuple[User | None, list[User]]:
    """Serialize role/status changes and lock active admins in stable order."""
    active_admins = (
        db.query(User)
        .filter(User.role == "admin", User.is_active.is_(True))
        .order_by(User.id)
        .with_for_update()
        .populate_existing()
        .all()
    )
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    return user, active_admins


def _ensure_active_admin_remains(
    user: User,
    active_admins: list[User],
    *,
    new_role: str | None = None,
    new_active: bool | None = None,
) -> None:
    effective_role = user.role if new_role is None else new_role
    effective_active = user.is_active if new_active is None else new_active
    removes_active_admin = (
        user.role == "admin"
        and user.is_active
        and (effective_role != "admin" or not effective_active)
    )
    if removes_active_admin and len(active_admins) <= 1:
        raise HTTPException(
            status_code=400,
            detail="At least one active administrator must remain",
        )


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
    _audit(db, current_user.username, "user_created", f"{user.username}: {user.role}")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username or email already registered") from exc
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    requested = data.model_dump(exclude_unset=True)
    if "role" in requested or "is_active" in requested:
        user, active_admins = _lock_user_management_rows(db, user_id)
    else:
        user = db.get(User, user_id)
        active_admins = []
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot edit own account from user administration")

    changes = requested
    if active_admins:
        _ensure_active_admin_remains(
            user,
            active_admins,
            new_role=changes.get("role"),
            new_active=changes.get("is_active"),
        )
    username = changes.get("username")
    email = changes.get("email")
    duplicate_conditions = []
    if username is not None:
        duplicate_conditions.append(User.username == username)
    if email is not None:
        duplicate_conditions.append(User.email == email)
    if duplicate_conditions and db.query(User).filter(
        User.id != user_id,
        or_(*duplicate_conditions),
    ).first():
        raise HTTPException(status_code=400, detail="Username or email already registered")

    change_details = []
    if "username" in changes and changes["username"] != user.username:
        change_details.append(f"username {user.username} -> {changes['username']}")
        user.username = changes["username"]
    if "email" in changes and changes["email"] != user.email:
        change_details.append("email cleared" if changes["email"] is None else "email updated")
        user.email = changes["email"]
    if "role" in changes and changes["role"] != user.role:
        change_details.append(f"role {user.role} -> {changes['role']}")
        user.role = changes["role"]
    if "is_active" in changes and changes["is_active"] != user.is_active:
        old_status = "active" if user.is_active else "inactive"
        new_status = "active" if changes["is_active"] else "inactive"
        change_details.append(f"status {old_status} -> {new_status}")
        user.is_active = changes["is_active"]
    if "password" in changes:
        user.hashed_password = get_password_hash(changes["password"])
        change_details.append("password reset")

    if not change_details:
        return user

    _audit(
        db,
        current_user.username,
        "user_updated",
        f"{user.username}: {', '.join(change_details)}",
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username or email already registered") from exc
    db.refresh(user)
    return user


@router.put("/users/{user_id}/role", response_model=UserOut)
def update_user_role(user_id: int, data: UserRoleUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin"))):
    user, active_admins = _lock_user_management_rows(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == current_user.id:
        raise HTTPException(400, "Cannot change own role")
    _ensure_active_admin_remains(user, active_admins, new_role=data.role)
    old_role = user.role
    user.role = data.role
    _audit(db, current_user.username, "user_role_updated", f"{user.username}: {old_role} -> {user.role}")
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}/status", response_model=UserOut)
def update_user_status(
    user_id: int,
    data: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    user, active_admins = _lock_user_management_rows(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == current_user.id and not data.is_active:
        raise HTTPException(400, "Cannot deactivate own account")
    _ensure_active_admin_remains(user, active_admins, new_active=data.is_active)
    old_status = "active" if user.is_active else "inactive"
    user.is_active = data.is_active
    new_status = "active" if user.is_active else "inactive"
    _audit(
        db,
        current_user.username,
        "user_status_updated",
        f"{user.username}: {old_status} -> {new_status}",
    )
    db.commit()
    db.refresh(user)
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
