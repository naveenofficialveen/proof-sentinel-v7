from datetime import datetime, timezone
from sqlalchemy import String, Integer, BigInteger, ForeignKey, DateTime, Text, Float, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def now(): return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE", index=True)  # ACTIVE | LOCKED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_activity: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence = relationship("EvidenceFile", back_populates="user")

class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class EvidenceFile(Base):
    __tablename__ = "evidence_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(30), index=True)
    mime: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    integrity: Mapped[str | None] = mapped_column(String(40))  # Verified intact | Hash mismatch
    signature_status: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="uploaded", index=True)  # uploaded|queued|analyzing|completed|failed
    error: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    derived_from_id: Mapped[int | None] = mapped_column(Integer)  # set when this file was made by the metadata remover/editor
    derived_op: Mapped[str | None] = mapped_column(String(30))     # metadata_removed | metadata_edited
    derived_note: Mapped[str | None] = mapped_column(Text)
    user = relationship("User", back_populates="evidence")
    metadata_row = relationship("MetadataRecord", uselist=False, cascade="all,delete")
    analysis = relationship("AnalysisResult", uselist=False, cascade="all,delete")
    ocr = relationship("OCRResult", uselist=False, cascade="all,delete")
    reports = relationship("Report", cascade="all,delete")

class MetadataRecord(Base):
    __tablename__ = "metadata"
    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence_files.id"), unique=True)
    data: Mapped[dict] = mapped_column(JSONB)

class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence_files.id"), unique=True)
    detection: Mapped[dict] = mapped_column(JSONB)
    structure: Mapped[list] = mapped_column(JSONB)
    signature: Mapped[dict] = mapped_column(JSONB)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class OCRResult(Base):
    __tablename__ = "ocr_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence_files.id"), unique=True)
    status: Mapped[str] = mapped_column(String(30))  # completed | no_text_detected | not_applicable | failed
    text: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    detail: Mapped[list | None] = mapped_column(JSONB)

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence_files.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SecurityLog(Base):
    __tablename__ = "security_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_type: Mapped[str] = mapped_column(String(10))  # user | admin | system
    actor_id: Mapped[int | None] = mapped_column(Integer)
    event: Mapped[str] = mapped_column(String(40), index=True)
    detail: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

class PasswordOtp(Base):
    __tablename__ = "password_otps"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    otp_hash: Mapped[str] = mapped_column(String(64))  # the 6-digit code itself is never stored
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

def log_event(db, actor_type, actor_id, event, detail=None, ip=None):
    db.add(SecurityLog(actor_type=actor_type, actor_id=actor_id, event=event, detail=detail, ip=ip))
    db.commit()


class BulkJob(Base):
    __tablename__ = "bulk_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(15), default="queued")  # queued | running | completed
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    source_ids: Mapped[list] = mapped_column(JSONB)
    results: Mapped[list] = mapped_column(JSONB, default=list)  # [{"source": id, "new": id | null, "error": str | null}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
