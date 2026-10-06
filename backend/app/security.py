from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
import base64, hashlib
import bcrypt
from fastapi import Response
from .config import settings

def _pre(p: str) -> bytes:
    # SHA-256 first, so any password length works with bcrypt's 72-byte limit
    return base64.b64encode(hashlib.sha256(p.encode("utf-8")).digest())

def hash_password(p: str) -> str:
    return bcrypt.hashpw(_pre(p), bcrypt.gensalt()).decode()

def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(_pre(p), h.encode())
    except ValueError:
        return False

def make_token(sub: int, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.token_minutes)
    return jwt.encode({"sub": str(sub), "role": role, "exp": exp}, settings.jwt_secret, algorithm="HS256")

def read_token(token: str, role: str) -> int | None:
    try:
        p = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        return None
    return int(p["sub"]) if p.get("role") == role else None

def set_cookie(resp: Response, name: str, token: str):
    resp.set_cookie(name, token, httponly=True, samesite="lax", secure=settings.cookie_secure,
                    max_age=settings.token_minutes * 60, path="/")
