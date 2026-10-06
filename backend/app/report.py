import os, json
from xml.sax.saxutils import escape
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from .config import settings

def _tbl(rows):
    st = getSampleStyleSheet()["BodyText"]; st.fontSize = 8
    data = [[Paragraph(escape(str(k)), st), Paragraph(escape(str(v)), st)] for k, v in rows]
    t = Table(data, colWidths=[150, 340])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t

def build_pdf(ev, meta, analysis, ocr) -> str:
    os.makedirs(os.path.join(settings.evidence_dir, "reports"), exist_ok=True)
    path = os.path.join(settings.evidence_dir, "reports", f"report_{ev.id}_{int(datetime.now().timestamp())}.pdf")
    ss = getSampleStyleSheet(); H = ss["Heading2"]; B = ss["BodyText"]
    s = [Paragraph("Digital Proof Verification and Evidence Analysis System", ss["Title"]),
         Paragraph("Technical Evidence Report", ss["Heading3"]), Spacer(1, 8),
         Paragraph("Evidence information", H),
         _tbl([("Evidence ID", ev.id), ("File name", ev.original_name), ("Detected type", ev.mime or "Not Available"),
               ("Category", ev.category or "Not Available"), ("Size (bytes)", ev.size_bytes),
               ("Uploaded", ev.created_at.isoformat()), ("Analysis status", ev.status),
               ("Analysis timestamp", analysis.completed_at.isoformat() if analysis else "Not Available")]),
         Paragraph("Integrity (SHA-256)", H),
         _tbl([("SHA-256", ev.sha256), ("Integrity check", ev.integrity or "Not Available")]),
         Paragraph("Digital signature", H)]
    sig = analysis.signature if analysis else {}
    s.append(_tbl([("Status", sig.get("status", "Not Available")), ("Detail", sig.get("detail") or "Not Available")]))
    if ev.derived_op:
        s += [Paragraph("Derived file", H), _tbl([("Created by", "Metadata Remover" if ev.derived_op == "metadata_removed" else "Metadata Editor"),
                                                  ("Derived from evidence ID", ev.derived_from_id), ("Details", ev.derived_note or "Not Available")]),
              Paragraph("This file is a modified copy. The original upload was not changed and keeps its own SHA-256 hash.", B)]
    if meta and meta.get("camera"):
        s += [Paragraph("Camera / device information", H), _tbl(list(meta["camera"].items())),
              Paragraph("Reported by the file's own metadata, which can be edited. It is not proof of which device captured the file.", B)]
    fx = (meta or {}).get("forensics") or {}
    if fx and not fx.get("error"):
        rows = []
        if fx.get("magic"): rows.append(("File type check (magic bytes)", f"{fx['magic'].get('verdict')}: {fx['magic'].get('message')}"))
        if fx.get("dqt"): rows.append(("JPEG compression fingerprint", f"quality about {fx['dqt'].get('ijg_quality')}; {fx['dqt'].get('classification')}"))
        if fx.get("social"): rows.append(("Social-media trace", f"{fx['social'].get('verdict')}. " + " ".join(fx['social'].get('reasons', []))))
        if fx.get("ela"):
            if fx["ela"].get("error"):
                rows.append(("Error Level Analysis", "Unavailable: " + str(fx["ela"].get("error"))))
            elif fx["ela"].get("verdict"):
                rows.append(("Error Level Analysis", f"{fx['ela'].get('level', 'n/a')}: {fx['ela'].get('verdict')} (unusual area {fx['ela'].get('hot_area_percent', 0)}%, peak {fx['ela'].get('peak_error', 'n/a')})"))
        if fx.get("quality") and fx["quality"].get("label"): rows.append(("Quality gauge", f"{fx['quality'].get('score')}/100, {fx['quality'].get('label')}"))
        if fx.get("size_check") and fx["size_check"].get("message"): rows.append(("Size check", fx["size_check"]["message"]))
        if fx.get("filename"):
            fn = fx["filename"]
            if fn.get("matched"):
                rows.append(("File name pattern", f"{fn.get('pattern')} ({fn.get('family') or 'unknown family'})"))
            else:
                rows.append(("File name pattern", "No known naming convention"))
        if fx.get("privacy") and "score" in fx["privacy"]: rows.append(("Privacy score", f"{fx['privacy']['score']}/100 ({fx['privacy'].get('level')})"))
        # Bulk sanitization is a separate multi-file operation, not a property of one evidence file.
        rows.append(("Bulk sanitizer", "Available separately: Metadata Remover → Clean many files at once (background progress + ZIP download)"))
        if fx.get("geo"):
            lat, lon = fx["geo"]["lat"], fx["geo"]["lon"]
            map_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}"
            rows.append(("GPS position", f"{lat}, {lon}"))
            rows.append(("Map", map_url))
        if fx.get("doc_lock"):
            dl = fx["doc_lock"]
            rows.append(("Document lock", dl.get("status", "locked")))
            if dl.get("fields_sha256"): rows.append(("Document fields SHA-256", dl["fields_sha256"]))
            if dl.get("text_sha256"): rows.append(("OCR full-text SHA-256", dl["text_sha256"]))
            if dl.get("reason"): rows.append(("Document lock note", dl["reason"]))
        elif ocr and ocr.status == "no_text_detected":
            rows.append(("Document lock", "Not applicable: OCR found no readable document text"))
        elif ocr and ocr.status == "failed":
            rows.append(("Document lock", "Unavailable: OCR failed"))
        else:
            rows.append(("Document lock", "Not applicable for this file"))
        if rows:
            s += [Paragraph("Forensic indicators", H), _tbl(rows), Paragraph("These are indicators from the file's own data and are not proof of origin or tampering.", B)]
            if fx.get("geo"):
                lat, lon = fx["geo"]["lat"], fx["geo"]["lon"]
                map_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}"
                s.append(Paragraph(f'<link href="{escape(map_url)}">Open the GPS position in OpenStreetMap</link>', B))
    if meta:
        s += [Paragraph("Metadata", H), _tbl(list(meta.get("general", {}).items()) + list(meta.get("specific", {}).items()))]
        if meta.get("structure"):
            s += [Paragraph("File structure analysis", H),
                  _tbl([(i + 1, json.dumps(x)) for i, x in enumerate(meta["structure"][:60])])]
    else:
        s += [Paragraph("Metadata", H), Paragraph("Unsupported / Analysis Not Available", B)]
    s.append(Paragraph("OCR results", H))
    if ocr and ocr.status == "completed":
        s += [Paragraph(f"Status: completed. Mean confidence: {ocr.confidence}", B), Paragraph(escape(ocr.text or ""), B)]
    else:
        s.append(Paragraph(f"Status: {ocr.status if ocr else 'not_applicable'}. No readable text reported.", B))
    SimpleDocTemplate(path, pagesize=A4).build(s)
    return path
