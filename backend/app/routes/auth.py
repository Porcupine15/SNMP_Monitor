from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserLogin, Token, UserOut
from app.auth import clear_login_attempts, create_access_token, get_current_user, get_password_hash, login_allowed, password_token_version, pwd_context, record_failed_login, verify_password
from app.config import public_registration_enabled

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/registration-status")
def registration_status():
    return {"enabled": public_registration_enabled()}


@router.post("/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if not public_registration_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is disabled; ask an administrator to create the account",
        )

    conditions = [User.username == user.username]
    if user.email:
        conditions.append(User.email == user.email)
    existing = db.query(User).filter(or_(*conditions)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already registered")
    hashed = get_password_hash(user.password)
    db_user = User(username=user.username, email=user.email, hashed_password=hashed, role="viewer")
    db.add(db_user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username or email already registered") from exc
    db.refresh(db_user)
    return db_user


@router.post("/login", response_model=Token)
def login(request: Request, user: UserLogin, db: Session = Depends(get_db)):
    source_ip = request.client.host if request.client else "unknown"
    if not login_allowed(user.username):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts; try again later")
    db_user = db.query(User).filter(User.username == user.username).first()
    if not db_user or not db_user.is_active or not verify_password(user.password, db_user.hashed_password):
        record_failed_login(user.username)
        crud.add_audit_event(db, user.username, "login_failed", source_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})
    clear_login_attempts(user.username)
    # Transparently strengthen hashes created by older releases after a valid login.
    if pwd_context.needs_update(db_user.hashed_password):
        db_user.hashed_password = get_password_hash(user.password)
        db.commit()
    crud.add_audit_event(db, db_user.username, "login_succeeded", source_ip)
    return {
        "access_token": create_access_token(
            data={
                "sub": db_user.username,
                "pwd": password_token_version(db_user.hashed_password),
            }
        ),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserOut)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
