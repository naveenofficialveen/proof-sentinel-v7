import json, os, re, uuid, hashlib, shutil
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..config import settings
from ..db import get_db
from ..models import User, EvidenceFile, Report, BulkJob, log_event
from ..deps import current_user, ip_of
from ..worker import analyze_evidence, bulk_sanitize
from ..analyzers import detect as D, tools as T, selective as SEL, forensics as F

router = APIRouter(prefix="/api")

def _brief(e: EvidenceFile):
    return {"id": e.id, "name": e.original_name, "category": e.category, "mime": e.mime, "size": e.size_bytes,
            "sha256": e.sha256, "status": e.status, "integrity": e.integrity, "signature": e.signature_status,
            "created_at": e.created_at, "error": e.error, "has_report": bool(e.reports),
            "derived_op": e.derived_op, "derived_from": e.derived_from_id, "derived_note": e.derived_note}

def _own(db, user, eid) -> EvidenceFile:
    e = db.get(EvidenceFile, eid)
    if not e or e.user_id != user.id:  # never reveal other users' records
        raise HTTPException(404, "Not found")
    return e

@router.post("/evidence", status_code=202)
async def upload(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), u: User = Depends(current_user)):
    name = os.path.basename(file.filename or "")
    if not name or len(name) > 200 or re.search(r"[\x00-\x1f/\\]", name):
        raise HTTPException(400, "Invalid file name")
    tmp_dir = os.path.join(settings.evidence_dir, "tmp"); final_dir = os.path.join(settings.evidence_dir, str(u.id))
    os.makedirs(tmp_dir, exist_ok=True); os.makedirs(final_dir, exist_ok=True)
    tmp = os.path.join(tmp_dir, uuid.uuid4().hex)
    h, size, limit = hashlib.sha256(), 0, settings.max_upload_mb * 1024 * 1024
    try:
        with open(tmp, "wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > limit: raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB")
                h.update(chunk); f.write(chunk)
        if size == 0: raise HTTPException(400, "Empty file")
        final = os.path.join(final_dir, uuid.uuid4().hex)  # random stored name, original name kept in DB only
        shutil.move(tmp, final)
    finally:
        if os.path.exists(tmp): os.remove(tmp)  # temporary file deletion
    e = EvidenceFile(user_id=u.id, original_name=name, stored_path=final, size_bytes=size, sha256=h.hexdigest(), status="queued")
    db.add(e); db.commit()
    log_event(db, "user", u.id, "UPLOAD", f"evidence {e.id}", ip_of(request))
    analyze_evidence.delay(e.id)
    return _brief(e)

@router.get("/evidence")
def list_evidence(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = db.query(EvidenceFile).filter(EvidenceFile.user_id == u.id).order_by(EvidenceFile.created_at.desc()).all()
    return [_brief(e) for e in rows]

@router.get("/evidence/{eid}")
def detail(eid: int, db: Session = Depends(get_db), u: User = Depends(current_user)):
    e = _own(db, u, eid)
    out = _brief(e)
    out["metadata"] = e.metadata_row.data if e.metadata_row else None
    out["analysis"] = ({"detection": e.analysis.detection, "structure": e.analysis.structure, "signature": e.analysis.signature,
                        "completed_at": e.analysis.completed_at} if e.analysis else None)
    out["ocr"] = ({"status": e.ocr.status, "text": e.ocr.text, "confidence": e.ocr.confidence, "frames": e.ocr.detail} if e.ocr else None)
    out["report_id"] = e.reports[-1].id if e.reports else None
    return out

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), u: User = Depends(current_user)):
    q = db.query(EvidenceFile).filter(EvidenceFile.user_id == u.id, EvidenceFile.derived_from_id.is_(None))
    c = lambda *f: q.filter(*f).count()
    return {"total": q.count(), "images": c(EvidenceFile.category == "image"), "videos": c(EvidenceFile.category == "video"),
            "files": c(EvidenceFile.category.notin_(["image", "video"])), "completed": c(EvidenceFile.status == "completed"),
            "reports": db.query(Report).filter(Report.user_id == u.id).count()}

@router.get("/reports")
def reports(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = db.query(Report, EvidenceFile).join(EvidenceFile).filter(Report.user_id == u.id).order_by(Report.created_at.desc()).all()
    return [{"id": r.id, "evidence_id": e.id, "file": e.original_name, "created_at": r.created_at} for r, e in rows]

@router.get("/reports/{rid}/download")
def download(rid: int, request: Request, db: Session = Depends(get_db), u: User = Depends(current_user)):
    r = db.get(Report, rid)
    if not r or r.user_id != u.id or not os.path.exists(r.path):
        raise HTTPException(404, "Not found")
    log_event(db, "user", u.id, "REPORT_DOWNLOAD", f"report {r.id}", ip_of(request))
    return FileResponse(r.path, media_type="application/pdf", filename=f"evidence_report_{r.evidence_id}.pdf")

@router.get("/reports/{rid}/view")
def view(rid: int, db: Session = Depends(get_db), u: User = Depends(current_user)):
    r = db.get(Report, rid)
    if not r or r.user_id != u.id or not os.path.exists(r.path):
        raise HTTPException(404, "Not found")
    return FileResponse(r.path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@router.get("/evidence/{eid}/download")
def download_file(eid: int, request: Request, db: Session = Depends(get_db), u: User = Depends(current_user)):
    e = _own(db, u, eid)
    if not os.path.exists(e.stored_path): raise HTTPException(404, "Not found")
    log_event(db, "user", u.id, "FILE_DOWNLOAD", f"evidence {e.id}", ip_of(request))
    return FileResponse(e.stored_path, media_type="application/octet-stream", filename=e.original_name)

def _derive(db, u, src, dst, op, prefix, note, request):
    new = EvidenceFile(user_id=u.id, original_name=(prefix + src.original_name)[:255], stored_path=dst, size_bytes=os.path.getsize(dst),
                       sha256=D.sha256_file(dst), status="queued", derived_from_id=src.id, derived_op=op, derived_note=note[:4000])
    db.add(new); db.commit()
    log_event(db, "user", u.id, "METADATA_REMOVED" if op == "metadata_removed" else "METADATA_EDITED", f"evidence {src.id} -> {new.id}", ip_of(request))
    analyze_evidence.delay(new.id)
    return _brief(new)

@router.post("/evidence/{eid}/remove-metadata", status_code=202)
def remove_metadata(eid: int, request: Request, db: Session = Depends(get_db), u: User = Depends(current_user)):
    e = _own(db, u, eid)
    info = D.detect(e.stored_path, e.original_name)
    kind = T.kind_of(info, "remove")
    if not kind: raise HTTPException(400, "Metadata removal is not supported for this file type")
    try:
        dst, note = T.remove(e.stored_path, os.path.join(settings.evidence_dir, str(u.id)), kind, info["extension"])
    except T.ToolError as x:
        raise HTTPException(400, str(x))
    return _derive(db, u, e, dst, "metadata_removed", "clean_", note, request)

@router.get("/evidence/{eid}/editable")
def editable(eid: int, db: Session = Depends(get_db), u: User = Depends(current_user)):
    e = _own(db, u, eid)
    info = D.detect(e.stored_path, e.original_name)
    kind = T.kind_of(info, "edit")
    if not kind: raise HTTPException(400, "Metadata editing is not supported for this file type. Supported: JPEG images, PDF, DOCX/XLSX/PPTX, audio and video.")
    try: cur = T.read_fields(e.stored_path, kind)
    except Exception: cur = {}
    return {"kind": kind, "can_remove_gps": kind == "jpeg", "fields": [{"key": k, "label": l, "value": cur.get(k, "")} for k, l in T.EDIT_FIELDS[kind]], "notes": T.EDIT_NOTES[kind]}

class EditBody(BaseModel):
    fields: dict[str, str] = {}
    remove_gps: bool = False

@router.post("/evidence/{eid}/edit-metadata", status_code=202)
def edit_metadata(eid: int, body: EditBody, request: Request, db: Session = Depends(get_db), u: User = Depends(current_user)):
    e = _own(db, u, eid)
    info = D.detect(e.stored_path, e.original_name)
    kind = T.kind_of(info, "edit")
    if not kind: raise HTTPException(400, "Metadata editing is not supported for this file type")
    try:
        dst, diff = T.edit(e.stored_path, os.path.join(settings.evidence_dir, str(u.id)), kind, info["extension"], body.fields, body.remove_gps)
    except T.ToolError as x:
        raise HTTPException(400, str(x))
    return _derive(db, u, e, dst, "metadata_edited", "edited_", json.dumps(diff), request)


# ---------------- selective metadata remover ----------------
@router.get("/evidence/{eid}/removable")
def removable(eid: int, db: Session = Depends(get_db), u: User = Depends(current_user)):
    e = _own(db, u, eid)
    info = D.detect(e.stored_path, e.original_name)
    kind = T.kind_of(info, "remove")
    if not kind: raise HTTPException(400, "Metadata removal is not supported for this file type")
    try: its = SEL.items(e.stored_path, kind)
    except Exception: its = []
    return {"kind": kind, "items": its, "notes": SEL.KIND_NOTES.get(kind, [])}

class RemoveBody(BaseModel):
    keys: list[str]

@router.post("/evidence/{eid}/remove-selected", status_code=202)
def remove_selected(eid: int, body: RemoveBody, request: Request, db: Session = Depends(get_db), u: User = Depends(current_user)):
    e = _own(db, u, eid)
    info = D.detect(e.stored_path, e.original_name)
    kind = T.kind_of(info, "remove")
    if not kind: raise HTTPException(400, "Metadata removal is not supported for this file type")
    try:
        dst, note = SEL.remove(e.stored_path, os.path.join(settings.evidence_dir, str(u.id)), kind, info["extension"], set(body.keys[:60]))
    except T.ToolError as x:
        raise HTTPException(400, str(x))
    return _derive(db, u, e, dst, "metadata_removed", "clean_", note, request)

# ---------------- forensic helpers: ELA picture, map lookup ----------------
def _image_ev(db, u, eid) -> EvidenceFile:
    e = _own(db, u, eid)
    if e.category != "image" or not os.path.exists(e.stored_path): raise HTTPException(404, "Not found")
    return e

def _cache(u, eid, name): return os.path.join(settings.evidence_dir, "cache", str(u.id), f"{eid}_{name}")

@router.get("/evidence/{eid}/preview.jpg")
def preview(eid: int, db: Session = Depends(get_db), u: User = Depends(current_user)):
    e = _image_ev(db, u, eid); out = _cache(u, eid, "preview.jpg")
    if not os.path.exists(out):
        try: F.preview_jpg(e.stored_path, out)
        except Exception: raise HTTPException(400, "This picture cannot be previewed")
    return FileResponse(out, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

@router.get("/evidence/{eid}/ela.png")
def ela_layer(eid: int, db: Session = Depends(get_db), u: User = Depends(current_user)):
    e = _image_ev(db, u, eid)
    if e.mime != "image/jpeg": raise HTTPException(400, "ELA works on JPEG pictures only")
    out = _cache(u, eid, "ela.png")
    if not os.path.exists(out):
        try: F.ela_layer_png(e.stored_path, out)
        except Exception: raise HTTPException(400, "ELA could not be computed for this picture")
    return FileResponse(out, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})

@router.get("/evidence/{eid}/place")
def place(eid: int, request: Request, db: Session = Depends(get_db), u: User = Depends(current_user)):
    """Reverse geocoding. Only runs when the user presses the button, because it sends the coordinates to OpenStreetMap Nominatim."""
    import urllib.request, urllib.parse
    from ..ratelimit import limit
    limit(f"geo:{u.id}", 20, 600)
    e = _own(db, u, eid)
    g = ((e.metadata_row.data if e.metadata_row else {}) or {}).get("forensics", {}).get("geo")
    if not g: raise HTTPException(400, "This file has no GPS position")
    url = "https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode({"format": "jsonv2", "lat": g["lat"], "lon": g["lon"], "zoom": 16, "accept-language": "en"})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ProofSentinel/1.0 (evidence analysis)"}), timeout=8) as r:
            j = json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:
        raise HTTPException(502, "The place-name service could not be reached. The map still works.")
    log_event(db, "user", u.id, "GEO_LOOKUP", f"evidence {e.id}", ip_of(request))
    return {"name": j.get("display_name") or "No address found for this position", "address": j.get("address") or {}}

# ---------------- bulk sanitizer ----------------
class BulkBody(BaseModel):
    ids: list[int]

def _job_view(j: BulkJob):
    return {"id": j.id, "status": j.status, "total": j.total, "done": j.done, "failed": j.failed,
            "percent": int(100 * j.done / j.total) if j.total else 100, "results": j.results or [], "created_at": j.created_at}

@router.post("/bulk/clean", status_code=202)
def bulk_start(body: BulkBody, request: Request, db: Session = Depends(get_db), u: User = Depends(current_user)):
    ids = list(dict.fromkeys(body.ids))[:2000]
    if not ids: raise HTTPException(400, "Select at least one file")
    mine = {i for (i,) in db.query(EvidenceFile.id).filter(EvidenceFile.user_id == u.id, EvidenceFile.id.in_(ids)).all()}
    ids = [i for i in ids if i in mine]
    if not ids: raise HTTPException(404, "Not found")
    j = BulkJob(user_id=u.id, total=len(ids), source_ids=ids, results=[])
    db.add(j); db.commit()
    log_event(db, "user", u.id, "BULK_CLEAN_START", f"job {j.id}: {len(ids)} files", ip_of(request))
    bulk_sanitize.delay(j.id)
    return _job_view(j)

def _job(db, u, jid) -> BulkJob:
    j = db.get(BulkJob, jid)
    if not j or j.user_id != u.id: raise HTTPException(404, "Not found")
    return j

@router.get("/bulk/{jid}")
def bulk_status(jid: int, db: Session = Depends(get_db), u: User = Depends(current_user)):
    return _job_view(_job(db, u, jid))

@router.get("/bulk/{jid}/download")
def bulk_download(jid: int, request: Request, db: Session = Depends(get_db), u: User = Depends(current_user)):
    import tempfile, zipfile
    from starlette.background import BackgroundTask
    j = _job(db, u, jid)
    new_ids = [r["new"] for r in (j.results or []) if r.get("new")]
    if not new_ids: raise HTTPException(404, "No cleaned files in this job")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip"); tmp.close()
    used = set()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as z:
        for e in db.query(EvidenceFile).filter(EvidenceFile.user_id == u.id, EvidenceFile.id.in_(new_ids)).all():
            if not os.path.exists(e.stored_path): continue
            name = e.original_name
            if name in used: name = f"{e.id}_{name}"
            used.add(name); z.write(e.stored_path, name)
    log_event(db, "user", u.id, "BULK_DOWNLOAD", f"job {j.id}", ip_of(request))
    return FileResponse(tmp.name, media_type="application/zip", filename=f"clean_files_job{j.id}.zip", background=BackgroundTask(os.remove, tmp.name))
