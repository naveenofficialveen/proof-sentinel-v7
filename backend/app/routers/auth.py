import logging, secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from ..db import get_db
from ..config import settings
from ..mail import demo_allowed, mail_configured, send_mail
from ..otpcheck import evaluate, otp_hash
from ..ratelimit import limit
from ..models import User, Admin, PasswordOtp, log_event
from ..security import hash_password, verify_password, make_token, set_cookie
from ..deps import current_user, current_admin, ip_of

router = APIRouter(prefix="/api")

class SignUp(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

class SignIn(BaseModel):
    email: EmailStr
    password: str

class AdminLogin(BaseModel):
    username: str
    password: str

@router.post("/auth/signup", status_code=201)
def signup(body: SignUp, request: Request, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "Email already registered")
    u = User(name=body.name.strip(), email=body.email.lower(), password_hash=hash_password(body.password))
    db.add(u); db.commit()
    log_event(db, "user", u.id, "SIGNUP", None, ip_of(request))
    return {"ok": True}

@router.post("/auth/signin")
def signin(body: SignIn, request: Request, response: Response, db: Session = Depends(get_db)):
    limit(f"signin-ip:{ip_of(request)}", 30, 600); limit(f"signin-mail:{body.email.lower()}", 10, 600)
    u = db.query(User).filter(User.email == body.email.lower()).first()
    if not u or not verify_password(body.password, u.password_hash):
        log_event(db, "user", u.id if u else None, "LOGIN_FAILED", None, ip_of(request))
        raise HTTPException(401, "Invalid email or password")
    if u.status == "LOCKED":
        log_event(db, "user", u.id, "LOGIN_BLOCKED_LOCKED", None, ip_of(request))
        raise HTTPException(403, "ACCOUNT_LOCKED")
    set_cookie(response, "user_token", make_token(u.id, "user"))
    log_event(db, "user", u.id, "LOGIN", None, ip_of(request))
    return {"id": u.id, "name": u.name, "email": u.email}

@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db), u: User = Depends(current_user)):
    response.delete_cookie("user_token", path="/")
    log_event(db, "user", u.id, "LOGOUT", None, ip_of(request))
    return {"ok": True}

@router.get("/auth/me")
def me(u: User = Depends(current_user)):
    return {"id": u.id, "name": u.name, "email": u.email, "created_at": u.created_at}

@router.post("/admin/login")
def admin_login(body: AdminLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    limit(f"admin-ip:{ip_of(request)}", 10, 600)
    a = db.query(Admin).filter(Admin.username == body.username).first()
    if not a or not verify_password(body.password, a.password_hash):
        log_event(db, "admin", a.id if a else None, "ADMIN_LOGIN_FAILED", None, ip_of(request))
        raise HTTPException(401, "Invalid credentials")
    set_cookie(response, "admin_token", make_token(a.id, "admin"))
    log_event(db, "admin", a.id, "ADMIN_LOGIN", None, ip_of(request))
    return {"username": a.username}

@router.post("/admin/logout")
def admin_logout(request: Request, response: Response, db: Session = Depends(get_db), a: Admin = Depends(current_admin)):
    response.delete_cookie("admin_token", path="/")
    log_event(db, "admin", a.id, "ADMIN_LOGOUT", None, ip_of(request))
    return {"ok": True}


class Forgot(BaseModel):
    email: EmailStr

class Reset(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    password: str = Field(min_length=10, max_length=128)

@router.post("/auth/forgot")
def forgot(body: Forgot, request: Request, db: Session = Depends(get_db)):
    limit(f"forgot-ip:{ip_of(request)}", 8, 600)
    generic = {"ok": True, "message": "If an account exists for that email, a 6-digit code has been sent. It is valid for %d minutes." % settings.otp_minutes}
    u = db.query(User).filter(User.email == body.email.lower()).first()
    if not u:
        log_event(db, "user", None, "PASSWORD_OTP_UNKNOWN_EMAIL", None, ip_of(request))
        if demo_allowed():
            raise HTTPException(404, "No account was found for this email")
        return generic
    now = datetime.now(timezone.utc)
    last = db.query(PasswordOtp).filter(PasswordOtp.user_id == u.id).order_by(PasswordOtp.id.desc()).first()
    if last and (now - last.created_at).total_seconds() < settings.otp_resend_seconds:
        return generic  # resend cooldown: stops anyone from flooding a mailbox
    db.query(PasswordOtp).filter(PasswordOtp.user_id == u.id, PasswordOtp.used_at.is_(None)).delete()
    otp = f"{secrets.randbelow(1_000_000):06d}"
    db.add(PasswordOtp(user_id=u.id, otp_hash=otp_hash(otp, u.id, settings.jwt_secret), expires_at=now + timedelta(minutes=settings.otp_minutes)))
    db.commit()
    if demo_allowed():  # local test setup: hand the code straight to the page
        log_event(db, "user", u.id, "PASSWORD_OTP_DEMO", None, ip_of(request))
        return {**generic, "demo_code": otp}
    sent, reason = send_mail(u.email, "Your password reset code",
                     f"Your verification code is {otp}\n\nIt expires in {settings.otp_minutes} minutes. "
                     "If you did not ask to reset your password, ignore this e-mail and do not share this code with anyone.")
    log_event(db, "user", u.id, "PASSWORD_OTP_SENT" if sent else "PASSWORD_OTP_NOT_SENT", None if sent else (reason or "")[:250], ip_of(request))
    if not mail_configured():
        # local development only: no mail account is set up, so show the code in the server log instead
        logging.warning("MAIL NOT CONFIGURED. Password reset code for user %s is %s", u.id, otp)
    return generic

class VerifyOtp(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

def _latest_otp(db, email):
    u = db.query(User).filter(User.email == email.lower()).first()
    if not u:
        return None, None
    r = db.query(PasswordOtp).filter(PasswordOtp.user_id == u.id, PasswordOtp.used_at.is_(None)).order_by(PasswordOtp.id.desc()).first()
    return u, r

@router.post("/auth/verify-otp")
def verify_otp(body: VerifyOtp, request: Request, db: Session = Depends(get_db)):
    """Step 2 of 'forgot password': checks the code without using it up, so the new-password step can follow."""
    limit(f"verify-ip:{ip_of(request)}", 20, 600)
    u, r = _latest_otp(db, body.email)
    if not u or not evaluate(r, body.otp, u.id, settings.jwt_secret):
        if u and r: db.commit()  # saves the failed-attempt count
        if u: log_event(db, "user", u.id, "PASSWORD_OTP_FAILED", None, ip_of(request))
        raise HTTPException(400, "The code is invalid or has expired")
    return {"ok": True}

@router.post("/auth/reset")
def reset(body: Reset, request: Request, db: Session = Depends(get_db)):
    limit(f"reset-ip:{ip_of(request)}", 15, 600)
    u, r = _latest_otp(db, body.email)
    if not u or not evaluate(r, body.otp, u.id, settings.jwt_secret):
        if u and r: db.commit()
        if u: log_event(db, "user", u.id, "PASSWORD_OTP_FAILED", None, ip_of(request))
        raise HTTPException(400, "The code is invalid or has expired")
    u.password_hash = hash_password(body.password)
    r.used_at = datetime.now(timezone.utc)
    db.commit()
    log_event(db, "user", u.id, "PASSWORD_RESET_DONE", None, ip_of(request))
    return {"ok": True}

@router.get("/auth/mail-status")
def mail_status():
    return {"configured": mail_configured(), "demo": demo_allowed()}
