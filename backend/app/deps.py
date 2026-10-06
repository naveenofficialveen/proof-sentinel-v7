from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .db import get_db
from .models import User, Admin
from .security import read_token

def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = read_token(request.cookies.get("user_token", ""), "user")
    user = db.get(User, uid) if uid else None
    if not user:
        raise HTTPException(401, "Not authenticated")
    if user.status == "LOCKED":  # enforced server-side on every protected call
        raise HTTPException(403, "ACCOUNT_LOCKED")
    user.last_activity = datetime.now(timezone.utc)
    db.commit()
    return user

def current_admin(request: Request, db: Session = Depends(get_db)) -> Admin:
    aid = read_token(request.cookies.get("admin_token", ""), "admin")
    admin = db.get(Admin, aid) if aid else None
    if not admin:
        raise HTTPException(401, "Not authenticated")
    return admin

def ip_of(request: Request) -> str | None:
    return request.client.host if request.client else None
