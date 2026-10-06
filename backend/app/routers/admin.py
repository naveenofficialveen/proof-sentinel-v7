from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Admin, EvidenceFile, Report, SecurityLog, log_event
from ..config import settings
from ..deps import current_admin, ip_of
from ..mail import mail_configured
from ..ratelimit import limit
from ..security import hash_password, verify_password

router = APIRouter(prefix="/api/admin")

@router.get("/me")
def me(a: Admin = Depends(current_admin)):
    return {"username": a.username}

@router.get("/stats")
def stats(db: Session = Depends(get_db), a: Admin = Depends(current_admin)):
    ev = db.query(EvidenceFile)
    return {"users": db.query(User).count(), "active_users": db.query(User).filter(User.status == "ACTIVE").count(),
            "locked_users": db.query(User).filter(User.status == "LOCKED").count(), "files": ev.count(),
            "images": ev.filter(EvidenceFile.category == "image").count(), "videos": ev.filter(EvidenceFile.category == "video").count(),
            "processed": ev.filter(EvidenceFile.status == "completed").count(), "reports": db.query(Report).count()}

def _user_row(db, u):
    return {"id": u.id, "name": u.name, "email": u.email, "created_at": u.created_at, "status": u.status,
            "files": db.query(EvidenceFile).filter(EvidenceFile.user_id == u.id).count(), "last_activity": u.last_activity}

@router.get("/users")
def users(q: str = "", db: Session = Depends(get_db), a: Admin = Depends(current_admin)):
    qs = db.query(User)
    if q: qs = qs.filter(or_(User.email.ilike(f"%{q}%"), User.name.ilike(f"%{q}%")))
    return [_user_row(db, u) for u in qs.order_by(User.id).limit(500)]

@router.get("/users/{uid}")
def user_detail(uid: int, db: Session = Depends(get_db), a: Admin = Depends(current_admin)):
    u = db.get(User, uid)
    if not u: raise HTTPException(404, "Not found")
    ev = db.query(EvidenceFile).filter(EvidenceFile.user_id == uid).order_by(EvidenceFile.created_at.desc()).all()
    reps = db.query(Report).filter(Report.user_id == uid).order_by(Report.created_at.desc()).all()
    return {**_user_row(db, u), "images": sum(e.category == "image" for e in ev), "videos": sum(e.category == "video" for e in ev),
            "analysis_history": [{"id": e.id, "name": e.original_name, "status": e.status, "created_at": e.created_at} for e in ev],
            "report_history": [{"id": r.id, "evidence_id": r.evidence_id, "created_at": r.created_at} for r in reps]}

def _set_status(uid, status, event, request, db, a):
    u = db.get(User, uid)
    if not u: raise HTTPException(404, "Not found")
    u.status = status; db.commit()
    log_event(db, "admin", a.id, event, f"user {uid}", ip_of(request))
    return _user_row(db, u)

@router.post("/users/{uid}/lock")
def lock(uid: int, request: Request, db: Session = Depends(get_db), a: Admin = Depends(current_admin)):
    return _set_status(uid, "LOCKED", "USER_LOCKED", request, db, a)

@router.post("/users/{uid}/unlock")
def unlock(uid: int, request: Request, db: Session = Depends(get_db), a: Admin = Depends(current_admin)):
    return _set_status(uid, "ACTIVE", "USER_UNLOCKED", request, db, a)

SORTS = {"created_at": EvidenceFile.created_at, "size": EvidenceFile.size_bytes, "name": EvidenceFile.original_name, "status": EvidenceFile.status}

@router.get("/evidence")
def evidence(q: str = "", category: str = "", status: str = "", sort: str = "created_at", order: str = "desc",
             db: Session = Depends(get_db), a: Admin = Depends(current_admin)):
    qs = db.query(EvidenceFile, User.email).join(User)
    if q: qs = qs.filter(or_(EvidenceFile.original_name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    if category: qs = qs.filter(EvidenceFile.category == category)
    if status: qs = qs.filter(EvidenceFile.status == status)
    col = SORTS.get(sort, EvidenceFile.created_at)
    qs = qs.order_by(col.asc() if order == "asc" else col.desc()).limit(500)
    return [{"id": e.id, "name": e.original_name, "user": email, "category": e.category, "mime": e.mime, "size": e.size_bytes,
             "created_at": e.created_at, "status": e.status, "verification": e.integrity, "signature": e.signature_status,
             "sha256": e.sha256} for e, email in qs]

@router.get("/reports")
def reports(db: Session = Depends(get_db), a: Admin = Depends(current_admin)):
    rows = db.query(Report, EvidenceFile, User.email).join(EvidenceFile, Report.evidence_id == EvidenceFile.id).join(User, Report.user_id == User.id).order_by(Report.created_at.desc()).limit(500)
    return [{"id": r.id, "file": e.original_name, "user": email, "analysis_status": e.status, "created_at": r.created_at} for r, e, email in rows]

@router.get("/logs")
def logs(event: str = "", limit: int = Query(200, le=1000), db: Session = Depends(get_db), a: Admin = Depends(current_admin)):
    qs = db.query(SecurityLog)
    if event: qs = qs.filter(SecurityLog.event == event)
    return [{"id": l.id, "actor_type": l.actor_type, "actor_id": l.actor_id, "event": l.event, "detail": l.detail,
             "created_at": l.created_at} for l in qs.order_by(SecurityLog.id.desc()).limit(limit)]


@router.get("/mail")
def mail_info(a: Admin = Depends(current_admin)):
    return {"configured": mail_configured(), "host": settings.smtp_host, "port": settings.smtp_port,
            "user": settings.smtp_user, "from": settings.smtp_from or settings.smtp_user}

class ChangePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

@router.post("/change-password")
def change_password(body: ChangePassword, request: Request, db: Session = Depends(get_db), a: Admin = Depends(current_admin)):
    limit(f"adminpw:{a.id}", 5, 600)
    if not verify_password(body.current_password, a.password_hash):
        log_event(db, "admin", a.id, "ADMIN_PASSWORD_CHANGE_FAILED", None, ip_of(request))
        raise HTTPException(400, "The current password is not correct")
    if body.current_password == body.new_password:
        raise HTTPException(400, "The new password must be different from the current one")
    a.password_hash = hash_password(body.new_password)
    db.commit()
    log_event(db, "admin", a.id, "ADMIN_PASSWORD_CHANGED", None, ip_of(request))
    return {"ok": True, "message": "Password changed. Use the new password the next time you sign in."}
