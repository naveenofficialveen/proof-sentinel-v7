"""Metadata remover / editor. Never touches the original: every function writes a NEW file.
JPEG/PNG: segments/chunks are dropped or replaced byte-for-byte (pixels are not re-encoded).
Office: docProps XML rewritten. PDF: pypdf. Audio/video: ffmpeg stream copy (no re-encode)."""
import json, os, re, subprocess, uuid, zipfile
from datetime import datetime
from xml.etree import ElementTree as ET
from PIL import Image

class ToolError(Exception):
    pass

def kind_of(info: dict, op: str):
    c, mime = info["category"], info["mime"]
    if c == "image":
        if mime == "image/jpeg": return "jpeg"
        return ("png" if mime == "image/png" else "image_other") if op == "remove" else None
    if c == "pdf": return "pdf"
    if c == "office_xml": return "office"
    if c in ("video", "audio"): return "media"
    return None

EDIT_FIELDS = {
    "jpeg": [("Make", "Camera make"), ("Model", "Camera model"), ("Software", "Software"), ("Artist", "Artist / author"),
             ("Copyright", "Copyright"), ("ImageDescription", "Description"), ("DateTimeOriginal", "Date taken (YYYY-MM-DD HH:MM:SS)")],
    "pdf": [("Title", "Title"), ("Author", "Author"), ("Subject", "Subject"), ("Keywords", "Keywords"), ("Creator", "Creator"), ("Producer", "Producer")],
    "office": [("title", "Title"), ("creator", "Author"), ("lastModifiedBy", "Last modified by"), ("subject", "Subject"), ("keywords", "Keywords"), ("description", "Comments"), ("category", "Category")],
    "media": [("title", "Title"), ("artist", "Artist"), ("comment", "Comment"), ("copyright", "Copyright"), ("creation_time", "Creation time (YYYY-MM-DD HH:MM:SS)")],
}
EDIT_NOTES = {
    "jpeg": ["Only the EXIF block is rewritten. Pixels are not re-encoded.", "XMP, IPTC and maker notes are not changed, so they may still hold the original values."],
    "pdf": ["Document information fields are changed. Page content is not changed.", "An embedded XMP block, if present, may still hold the original values."],
    "office": ["Document properties are changed. Document content is not changed."],
    "media": ["The streams are copied without re-encoding. Only container metadata is changed."],
}

def _clean_text(v: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", str(v)).strip()[:500]

# ---------------- JPEG ----------------
def jpeg_split(data: bytes):
    if data[:2] != b"\xff\xd8":
        raise ToolError("This is not a valid JPEG file")
    segs, i = [], 2
    while i + 4 <= len(data):
        if data[i] != 0xFF: break
        m = data[i + 1]
        if m == 0xFF: i += 1; continue
        if m in (0xD9, 0xDA): break
        if m == 0x01 or 0xD0 <= m <= 0xD7:
            segs.append((m, data[i:i + 2])); i += 2; continue
        ln = int.from_bytes(data[i + 2:i + 4], "big")
        segs.append((m, data[i:i + 2 + ln])); i += 2 + ln
    return segs, data[i:]

def _app1(payload: bytes) -> bytes:
    if len(payload) > 65533: raise ToolError("Metadata block is too large")
    return b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload

def _join(segs, tail, new_app1=None) -> bytes:
    out, placed = bytearray(b"\xff\xd8"), new_app1 is None
    for m, seg in segs:
        if not placed and m != 0xE0:  # EXIF goes right after SOI/JFIF
            out += new_app1; placed = True
        out += seg
    if not placed: out += new_app1
    return bytes(out) + tail

def _is_exif(m, seg): return m == 0xE1 and seg[4:10] == b"Exif\x00\x00"

def strip_jpeg(src, dst):
    data = open(src, "rb").read()
    segs, tail = jpeg_split(data)
    with Image.open(src) as im:
        orientation = im.getexif().get(0x0112)
    keep, removed = [], 0
    for m, seg in segs:
        drop = m == 0xE1 or 0xE3 <= m <= 0xED or m in (0xEF, 0xFE) or (m == 0xE2 and seg[4:16] != b"ICC_PROFILE\x00")
        if drop: removed += len(seg)
        else: keep.append((m, seg))
    eoi = tail.find(b"\xff\xd9")  # phones append extra data (motion video, vendor trailers) after the image end
    if eoi >= 0 and len(tail) > eoi + 2: removed += len(tail) - eoi - 2; tail = tail[:eoi + 2]
    new = None
    if orientation and orientation != 1:  # keep display direction correct
        ex = Image.Exif(); ex[0x0112] = orientation
        new = _app1(ex.tobytes())
    open(dst, "wb").write(_join(keep, tail, new))
    return f"Removed {removed} bytes of EXIF, XMP, IPTC, comment and trailing data" + (" (orientation kept)" if new else "")

def edit_jpeg(src, dst, changes: dict, remove_gps: bool = False):
    data = open(src, "rb").read()
    segs, tail = jpeg_split(data)
    with Image.open(src) as im:
        ex = im.getexif()
        ifd0 = {"Make": 0x010F, "Model": 0x0110, "Software": 0x0131, "Artist": 0x013B, "Copyright": 0x8298, "ImageDescription": 0x010E}
        old = {}
        if remove_gps:
            old["GPS location"] = "Present" if 0x8825 in ex else "Not present"
            if 0x8825 in ex: del ex[0x8825]
        for k, v in changes.items():
            if k == "DateTimeOriginal":
                sub = ex.get_ifd(0x8769)
                old[k] = sub.get(0x9003)
                if v: sub[0x9003] = v
                else: sub.pop(0x9003, None)
            else:
                old[k] = ex.get(ifd0[k])
                if v: ex[ifd0[k]] = v
                elif ifd0[k] in ex: del ex[ifd0[k]]
        payload = ex.tobytes()
    keep = [(m, s) for m, s in segs if not _is_exif(m, s)]
    open(dst, "wb").write(_join(keep, tail, _app1(payload)))
    return old

# ---------------- PNG / other images ----------------
def strip_png(src, dst):
    d = open(src, "rb").read()
    if d[:8] != b"\x89PNG\r\n\x1a\n": raise ToolError("This is not a valid PNG file")
    out, i, removed = bytearray(d[:8]), 8, 0
    while i + 12 <= len(d):
        ln = int.from_bytes(d[i:i + 4], "big"); typ = d[i + 4:i + 8]; end = i + 12 + ln
        if typ in (b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"): removed += end - i
        else: out += d[i:end]
        i = end
        if typ == b"IEND": break
    open(dst, "wb").write(bytes(out))
    return f"Removed {removed} bytes of text, EXIF and timestamp chunks"

def strip_image_other(src, dst):
    with Image.open(src) as im:
        if getattr(im, "n_frames", 1) > 1:
            raise ToolError("Animated or multi-page images are not supported by the remover")
        fmt = im.format
        clean = im.copy(); clean.info.clear()
        kw = {"lossless": True} if fmt == "WEBP" else {}
        clean.save(dst, format=fmt, **kw)
    return f"Image re-saved as {fmt} without embedded metadata (lossless re-encode)"

# ---------------- PDF ----------------
def strip_pdf(src, dst):
    from pypdf import PdfReader, PdfWriter
    r = PdfReader(src)
    if r.is_encrypted: raise ToolError("Encrypted PDF files are not supported")
    w = PdfWriter()
    for p in r.pages: w.add_page(p)
    w.add_metadata({"/Producer": ""})
    with open(dst, "wb") as f: w.write(f)
    return "Document information and XMP metadata were not copied to the new file"

def edit_pdf(src, dst, changes):
    from pypdf import PdfReader, PdfWriter
    r = PdfReader(src)
    if r.is_encrypted: raise ToolError("Encrypted PDF files are not supported")
    old_meta = {str(k): str(v) for k, v in (r.metadata or {}).items()}
    w = PdfWriter(clone_from=src)
    meta = dict(old_meta)
    old = {}
    for k, v in changes.items():
        old[k] = old_meta.get("/" + k)
        if v: meta["/" + k] = v
        else: meta.pop("/" + k, None)
    w.metadata = None
    w.add_metadata(meta)
    with open(dst, "wb") as f: w.write(f)
    return old

# ---------------- Office (docx/xlsx/pptx) ----------------
NS = {"cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties", "dc": "http://purl.org/dc/elements/1.1/",
      "dcterms": "http://purl.org/dc/terms/", "dcmitype": "http://purl.org/dc/dcmitype/", "xsi": "http://www.w3.org/2001/XMLSchema-instance"}
for _p, _u in NS.items(): ET.register_namespace(_p, _u)
APP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
CORE_TAG = {"title": "dc:title", "subject": "dc:subject", "creator": "dc:creator", "description": "dc:description",
            "keywords": "cp:keywords", "lastModifiedBy": "cp:lastModifiedBy", "category": "cp:category"}

def _q(t): p, n = t.split(":"); return f"{{{NS[p]}}}{n}"

def _office_rewrite(src, dst, core: dict, blank_app: bool, blank_custom: bool):
    old = {}
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/core.xml":
                root = ET.fromstring(data)
                for k, v in core.items():
                    el = root.find(_q(CORE_TAG[k]))
                    old[k] = el.text if el is not None else None
                    if v:
                        if el is None: el = ET.SubElement(root, _q(CORE_TAG[k]))
                        el.text = v
                    elif el is not None:
                        el.text = ""
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            elif item.filename == "docProps/app.xml" and blank_app:
                ET.register_namespace("", APP_NS)
                root = ET.fromstring(data)
                for t in ("Company", "Manager", "HyperlinkBase"):
                    el = root.find(f"{{{APP_NS}}}{t}")
                    if el is not None: el.text = ""
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            elif item.filename == "docProps/custom.xml" and blank_custom:
                root = ET.fromstring(data)
                for child in list(root): root.remove(child)
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(item, data)
    return old

def strip_office(src, dst):
    blank = {k: "" for k in ("title", "subject", "creator", "description", "keywords", "lastModifiedBy", "category")}
    _office_rewrite(src, dst, blank, True, True)
    return "Author, title, subject, keywords, comments, company and custom properties were cleared"

def edit_office(src, dst, changes):
    return _office_rewrite(src, dst, changes, False, False)

# ---------------- Audio / video via ffmpeg ----------------
def _ffmpeg(args):
    try:
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        raise ToolError("Processing took too long")
    if r.returncode != 0:
        raise ToolError("This audio/video file could not be processed (unsupported or damaged container)")

def strip_media(src, dst):
    _ffmpeg(["-i", src, "-map", "0:v?", "-map", "0:a?", "-map", "0:s?", "-map_metadata", "-1", "-map_chapters", "-1",
             "-map_metadata:s:v", "-1", "-map_metadata:s:a", "-1", "-c", "copy",
             "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", dst])
    return "Container, stream and chapter metadata were removed (streams copied without re-encoding)"

def edit_media(src, dst, changes):
    args = ["-i", src, "-map", "0:v?", "-map", "0:a?", "-map", "0:s?", "-map_metadata", "0", "-c", "copy"]
    for k, v in changes.items(): args += ["-metadata", f"{k}={v}"]
    _ffmpeg(args + [dst])
    return {}

# ---------------- reading current values for the editor form ----------------
def read_fields(path, kind) -> dict:
    keys = [k for k, _ in EDIT_FIELDS[kind]]
    cur = {}
    if kind == "jpeg":
        with Image.open(path) as im:
            ex = im.getexif()
            m = {"Make": 0x010F, "Model": 0x0110, "Software": 0x0131, "Artist": 0x013B, "Copyright": 0x8298, "ImageDescription": 0x010E}
            for k, t in m.items():
                if isinstance(ex.get(t), str): cur[k] = ex[t].strip("\x00 ")
            d = ex.get_ifd(0x8769).get(0x9003)
            if isinstance(d, str): cur["DateTimeOriginal"] = d.replace(":", "-", 2)
    elif kind == "pdf":
        from pypdf import PdfReader
        for k, v in (PdfReader(path).metadata or {}).items():
            if str(k).lstrip("/") in keys: cur[str(k).lstrip("/")] = str(v)
    elif kind == "office":
        with zipfile.ZipFile(path) as z:
            if "docProps/core.xml" in z.namelist():
                root = ET.fromstring(z.read("docProps/core.xml"))
                for k, t in CORE_TAG.items():
                    el = root.find(_q(t))
                    if el is not None and el.text and k in keys: cur[k] = el.text
    elif kind == "media":
        r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", path], capture_output=True, text=True, timeout=120)
        try: tags = {k.lower(): v for k, v in json.loads(r.stdout).get("format", {}).get("tags", {}).items()}
        except Exception: tags = {}
        for k in keys:
            if tags.get(k): cur[k] = tags[k]
    return cur

# ---------------- public entry points ----------------
def _validate(kind, changes: dict, allow_empty: bool = False) -> dict:
    allowed = {k for k, _ in EDIT_FIELDS[kind]}
    out = {}
    for k, v in changes.items():
        if k not in allowed: raise ToolError(f"Field '{k}' cannot be edited for this file type")
        v = _clean_text(v)
        if v and k == "DateTimeOriginal":
            try: v = datetime.strptime(v.replace("T", " ").replace(":", "-", 2) if v[4] == ":" else v, "%Y-%m-%d %H:%M:%S").strftime("%Y:%m:%d %H:%M:%S")
            except ValueError: raise ToolError("Date must look like 2026-10-02 13:52:50")
        if v and k == "creation_time":
            try: v = datetime.strptime(v.replace("T", " ").rstrip("Z").split(".")[0], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%dT%H:%M:%S.000000Z")
            except ValueError: raise ToolError("Creation time must look like 2026-10-02 13:52:50")
        out[k] = v
    if not out and not allow_empty: raise ToolError("No changes were provided")
    return out

def _out_path(directory, ext, keep_ext):
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, uuid.uuid4().hex + (("." + ext) if keep_ext and ext else ""))

def remove(src, directory, kind, ext):
    dst = _out_path(directory, ext, kind == "media")
    try:
        note = {"jpeg": strip_jpeg, "png": strip_png, "image_other": strip_image_other, "pdf": strip_pdf,
                "office": strip_office, "media": strip_media}[kind](src, dst)
    except ToolError:
        if os.path.exists(dst): os.remove(dst)
        raise
    except Exception:
        if os.path.exists(dst): os.remove(dst)
        raise ToolError("This file could not be processed. It may be damaged or unsupported.")
    return dst, note

def edit(src, directory, kind, ext, changes, remove_gps=False):
    remove_gps = bool(remove_gps and kind == "jpeg")
    changes = _validate(kind, changes, allow_empty=remove_gps)
    dst = _out_path(directory, ext, kind == "media")
    try:
        old = edit_jpeg(src, dst, changes, remove_gps) if kind == "jpeg" else {"pdf": edit_pdf, "office": edit_office, "media": edit_media}[kind](src, dst, changes)
    except ToolError:
        if os.path.exists(dst): os.remove(dst)
        raise
    except Exception:
        if os.path.exists(dst): os.remove(dst)
        raise ToolError("This file could not be processed. It may be damaged or unsupported.")
    cur = read_fields(src, kind) if kind == "media" else {}
    diff = {k: {"old": str((old.get(k) if old.get(k) is not None else cur.get(k)) or "Not set"), "new": v or "Removed"} for k, v in changes.items()}
    if remove_gps: diff["GPS location"] = {"old": old.get("GPS location", "Unknown"), "new": "Removed"}
    return dst, diff
