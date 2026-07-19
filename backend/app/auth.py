import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Optional
import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User

# Чтение из переменных окружения
SECRET_KEY = os.getenv("SECRET_KEY", "secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
TOKEN_ISSUER = os.getenv("TOKEN_ISSUER", "snmp-monitor")
TOKEN_AUDIENCE = os.getenv("TOKEN_AUDIENCE", "snmp-monitor-web")

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
    pbkdf2_sha256__default_rounds=600_000,
)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
_login_attempts: dict[str, list[float]] = {}

def login_allowed(username: str) -> bool:
    now = time.time()
    attempts = [item for item in _login_attempts.get(username, []) if now - item < 300]
    _login_attempts[username] = attempts
    return len(attempts) < 5

def record_failed_login(username: str) -> None:
    _login_attempts.setdefault(username, []).append(time.time())

def clear_login_attempts(username: str) -> None:
    _login_attempts.pop(username, None)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)


def password_token_version(hashed_password: str) -> str:
    """Bind access tokens to the current password hash without exposing it."""
    return sha256(hashed_password.encode("utf-8")).hexdigest()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    issued_at = datetime.now(timezone.utc)
    if expires_delta:
        expire = issued_at + expires_delta
    else:
        expire = issued_at + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": expire,
        "iat": issued_at,
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
        "jti": secrets.token_urlsafe(18),
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=TOKEN_AUDIENCE,
            issuer=TOKEN_ISSUER,
        )
        username: str = payload.get("sub")
        password_version: str = payload.get("pwd")
        if username is None or password_version is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if (
        user is None
        or not user.is_active
        or not secrets.compare_digest(
            password_version,
            password_token_version(user.hashed_password),
        )
    ):
        raise credentials_exception
    return user


def require_roles(*roles: str):
    async def role_guard(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user
    return role_guard
