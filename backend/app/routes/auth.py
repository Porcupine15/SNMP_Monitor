import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserLogin, Token, UserOut
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user, login_allowed, record_failed_login, clear_login_attempts

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    user_count = db.query(User).count()
    public_registration = os.getenv("ALLOW_PUBLIC_REGISTRATION", "false").lower() in {"1", "true", "yes"}
    if user_count and not public_registration:
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
    role = "admin" if user_count == 0 else "viewer"
    db_user = User(username=user.username, email=user.email, hashed_password=hashed, role=role)
    db.add(db_user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username or email already registered") from exc
    db.refresh(db_user)
    return db_user


@router.post("/login", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    if not login_allowed(user.username):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts; try again later")
    db_user = db.query(User).filter(User.username == user.username).first()
    if not db_user or not db_user.is_active or not verify_password(user.password, db_user.hashed_password):
        record_failed_login(user.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})
    clear_login_attempts(user.username)
    return {"access_token": create_access_token(data={"sub": db_user.username}), "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
