import os
from celery import Celery
from .analyzers import detect as D, metadata as M, signature as S, ocr as O, forensics as F

celery_app = Celery("proof", broker=os.environ["REDIS_URL"], backend=os.environ["REDIS_URL"])

def run_analysis(path: str, filename: str) -> dict:
    info = D.detect(path, filename)
    result = {"detection": info, "sha256": D.sha256_file(path), "signature": S.check(path, info), "metadata": None, "ocr": None}
    if info["supported"]:
        result["metadata"] = M.extract(path, filename, info)
        if info["category"] == "image": result["ocr"] = O.ocr_image_file(path)
        elif info["category"] == "video": result["ocr"] = O.ocr_video_frames(path)
        try:
            result["metadata"]["forensics"] = F.compute(path, filename, info, result["metadata"].get("specific"),
                                                               (result["ocr"] or {}).get("text"))
            # Preserve OCR outcome explicitly for the Document Lock UI/report.
            if result["metadata"]["forensics"].get("doc_lock") and result["ocr"]:
                lock = result["metadata"]["forensics"]["doc_lock"]
                if result["ocr"].get("status") == "failed":
                    lock = {"status": "ocr_failed", "reason": "OCR could not process this image."}
                    result["metadata"]["forensics"]["doc_lock"] = lock
        except Exception:
            result["metadata"]["forensics"] = {"error": "Forensic checks could not run on this file"}
    return result

@celery_app.task
def analyze_evidence(evidence_id: int):
    from .db import SessionLocal
    from .models import EvidenceFile, MetadataRecord, AnalysisResult, OCRResult, Report, log_event
    from .report import build_pdf
    db = SessionLocal()
    ev = db.get(EvidenceFile, evidence_id)
    try:
        ev.status = "analyzing"; db.commit()
        r = run_analysis(ev.stored_path, ev.original_name)
        ev.category, ev.mime = r["detection"]["category"], r["detection"]["mime"]
        ev.integrity = "Verified intact (hash matches upload)" if r["sha256"] == ev.sha256 else "HASH MISMATCH"
        ev.signature_status = r["signature"]["status"]
        meta = r["metadata"]
        lock = (meta or {}).get("forensics", {}).get("doc_lock") if meta else None
        if lock and lock.get("status") == "locked": _compare_lock(db, ev, lock)
        db.add(AnalysisResult(evidence_id=ev.id, detection=r["detection"], structure=(meta or {}).get("structure", []), signature=r["signature"]))
        if meta: db.add(MetadataRecord(evidence_id=ev.id, data=meta))
        o = r["ocr"]
        if o is None: db.add(OCRResult(evidence_id=ev.id, status="not_applicable"))
        else: db.add(OCRResult(evidence_id=ev.id, status=o["status"], text=o.get("text"), confidence=o.get("confidence"), detail=o.get("frames")))
        db.commit(); db.refresh(ev)
        path = build_pdf(ev, meta, ev.analysis, ev.ocr)
        db.add(Report(evidence_id=ev.id, user_id=ev.user_id, path=path))
        ev.status = "completed"; db.commit()
        log_event(db, "user", ev.user_id, "ANALYSIS_DONE", f"evidence {ev.id}")
        log_event(db, "user", ev.user_id, "REPORT_GENERATED", f"evidence {ev.id}")
    except Exception:
        db.rollback()
        ev = db.get(EvidenceFile, evidence_id)
        ev.status, ev.error = "failed", "Analysis failed"; db.commit()
        log_event(db, "system", None, "ANALYSIS_FAILED", f"evidence {evidence_id}")
    finally:
        db.close()


def _compare_lock(db, ev, lock):
    """Document hash lock: compare the ID numbers and text fingerprint with this user's earlier documents."""
    from .models import EvidenceFile, MetadataRecord
    rows = (db.query(EvidenceFile, MetadataRecord).join(MetadataRecord, MetadataRecord.evidence_id == EvidenceFile.id)
            .filter(EvidenceFile.user_id == ev.user_id, EvidenceFile.id != ev.id).order_by(EvidenceFile.id.desc()).limit(300).all())
    compared, altered = [], False
    for e, m in rows:
        o = ((m.data or {}).get("forensics") or {}).get("doc_lock")
        if not o or o.get("status") not in ("locked", "match", "altered"): continue
        if e.sha256 == ev.sha256: compared.append({"evidence_id": e.id, "name": e.original_name, "result": "identical", "differences": []}); continue
        common = set(lock["ids"]) & set(o["ids"])
        if not common: continue
        if o["fields_sha256"] == lock["fields_sha256"]: compared.append({"evidence_id": e.id, "name": e.original_name, "result": "match", "differences": []}); continue
        diff = []
        if set(lock["ids"]) - set(o["ids"]): diff.append("ID numbers only in this file: " + ", ".join(sorted(set(lock["ids"]) - set(o["ids"]))))
        if set(o["ids"]) - set(lock["ids"]): diff.append("ID numbers only in the locked file: " + ", ".join(sorted(set(o["ids"]) - set(lock["ids"]))))
        if lock.get("name_guess") and o.get("name_guess") and lock["name_guess"] != o["name_guess"]: diff.append(f"Name differs: '{o['name_guess']}' (locked) vs '{lock['name_guess']}'")
        if lock["number_count"] != o["number_count"]: diff.append(f"Count of numbers differs: {o['number_count']} (locked) vs {lock['number_count']}")
        compared.append({"evidence_id": e.id, "name": e.original_name, "result": "altered", "differences": diff or ["The text fingerprint differs"]})
        altered = True
        if len(compared) >= 5: break
    lock["compared"] = compared[:5]
    lock["status"] = "altered" if altered else ("match" if compared else "locked")

@celery_app.task
def bulk_sanitize(job_id: int):
    """Cleans many files in the background. Progress is saved after every file so the page can show a live bar."""
    import os
    from .config import settings
    from .db import SessionLocal
    from .models import BulkJob, EvidenceFile, log_event
    from .analyzers import tools as T
    db = SessionLocal()
    try:
        job = db.get(BulkJob, job_id); job.status = "running"; db.commit()
        results, user_dir = [], os.path.join(settings.evidence_dir, str(job.user_id))
        for sid in job.source_ids:
            res = {"source": sid, "new": None, "error": None}
            try:
                src = db.get(EvidenceFile, sid)
                if not src or src.user_id != job.user_id: raise T.ToolError("File not found")
                info = D.detect(src.stored_path, src.original_name)
                kind = T.kind_of(info, "remove")
                if not kind: raise T.ToolError("Not supported for this file type")
                dst, note = T.remove(src.stored_path, user_dir, kind, info["extension"])
                new = EvidenceFile(user_id=job.user_id, original_name=("clean_" + src.original_name)[:255], stored_path=dst, size_bytes=os.path.getsize(dst),
                                   sha256=D.sha256_file(dst), status="queued", derived_from_id=src.id, derived_op="metadata_removed", derived_note=note[:4000])
                db.add(new); db.commit(); res["new"] = new.id
                analyze_evidence.delay(new.id)
            except T.ToolError as x: db.rollback(); res["error"] = str(x)
            except Exception: db.rollback(); res["error"] = "Could not be processed"
            results.append(res)
            job = db.get(BulkJob, job_id); job.done = len(results); job.failed = sum(1 for r in results if r["error"]); job.results = list(results); db.commit()
        job.status = "completed"; db.commit()
        log_event(db, "user", job.user_id, "BULK_CLEAN_DONE", f"job {job.id}: {job.done - job.failed} ok, {job.failed} failed")
    finally:
        db.close()
