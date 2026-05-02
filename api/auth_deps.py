import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import AdminUser
from services.auth_service import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_admin_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AdminUser:
    auth_disabled = os.getenv("ADMIN_AUTH_DISABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if auth_disabled:
        user = db.query(AdminUser).filter(AdminUser.is_active.is_(True)).order_by(AdminUser.id.asc()).first()
        if not user:
            raise HTTPException(status_code=401, detail="No active admin user found.")
        return user

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing auth token.")
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid auth token.") from exc

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload.")

    user = db.query(AdminUser).filter(AdminUser.username == username, AdminUser.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=401, detail="Admin user not found or inactive.")
    return user
