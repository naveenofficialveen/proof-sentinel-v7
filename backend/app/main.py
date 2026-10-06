import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import settings
from sqlalchemy import text
from .db import Base, engine, SessionLocal
from .models import Admin
from .security import hash_password
from .routers import auth, evidence, admin

app = FastAPI(title="Digital Proof Verification and Evidence Analysis System", docs_url=None, redoc_url=None)
LAN_ORIGINS = r"^http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+):3000$"
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True,
                   allow_origin_regex=None if settings.cookie_secure else LAN_ORIGINS,  # lets a phone on the same Wi-Fi test locally
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)  # use Alembic migrations for production
    with engine.begin() as c:  # add new columns to databases created by an earlier version
        for ddl in ("ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS derived_from_id INTEGER",
                    "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS derived_op VARCHAR(30)",
                    "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS derived_note TEXT"):
            c.execute(text(ddl))
    db = SessionLocal()
    if not db.query(Admin).filter(Admin.username == settings.admin_username).first():
        db.add(Admin(username=settings.admin_username, password_hash=hash_password(settings.admin_password))); db.commit()
    db.close()

@app.exception_handler(Exception)
async def safe_errors(request: Request, exc: Exception):
    logging.exception("Unhandled error")  # details stay in server logs only
    return JSONResponse({"detail": "Internal server error"}, status_code=500)

for r in (auth.router, evidence.router, admin.router):
    app.include_router(r)

@app.get("/api/health")
def health(): return {"ok": True}
