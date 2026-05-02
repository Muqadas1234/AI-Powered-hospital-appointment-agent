import os
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from db.models import AdminUser

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def get_jwt_secret() -> str:
    return os.getenv("JWT_SECRET_KEY", "change_this_in_production")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(subject: str, role: str, expires_minutes: int = 60) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])


def authenticate_admin_user(db: Session, username: str, password: str) -> AdminUser | None:
    user = db.query(AdminUser).filter(AdminUser.username == username).first()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def ensure_default_admin(db: Session) -> None:
    username = os.getenv("ADMIN_USERNAME", "admin").strip()
    password = os.getenv("ADMIN_PASSWORD", "admin123").strip()
    role = os.getenv("ADMIN_ROLE", "admin").strip() or "admin"

    existing = db.query(AdminUser).filter(AdminUser.username == username).first()
    if existing:
        return

    db.add(
        AdminUser(
            username=username,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
    )
    db.commit()
