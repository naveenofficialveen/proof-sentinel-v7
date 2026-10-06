"""Selective metadata removal. items() lists what the file really contains; remove() writes a NEW file without only the chosen items.
If every listed item is chosen, the full stripper in tools.py is used (it is the most thorough). Pixels are never re-encoded."""
import json, os, re, subprocess, zipfile
from xml.etree import ElementTree as ET
from PIL import Image
from . import tools as T

# ---- JPEG: EXIF tags belong to groups. (IFD0 tags, Exif-IFD tags)
JPEG_EXIF = {
    "device":   ("Camera make and model, lens", {0x010F, 0x0110}, {0xA432, 0xA433, 0xA434}),
    "datetime": ("Date and time taken", {0x0132}, {0x9003, 0x9004, 0x9010, 0x9011, 0x9012, 0x9290, 0x9291, 0x9292}),
    "software": ("Software and host computer", {0x0131, 0x013C}, set()),
    "person":   ("Author, owner and copyright", {0x013B, 0x8298}, {0xA430}),
    "serial":   ("Serial numbers and unique image ID", set(), {0xA431, 0xA435, 0xA420}),
    "describe": ("Description and user comment", {0x010E}, {0x9286}),
    "settings": ("Shooting settings (exposure, ISO, flash, focal length, white balance)", set(),
                 {0x829A, 0x829D, 0x8822, 0x8824, 0x8827, 0x8830, 0x8831, 0x8832, 0x9201, 0x9202, 0x9203, 0x9204, 0x9205, 0x9206, 0x9207, 0x9208,
                  0x9209, 0x920A, 0xA401, 0xA402, 0xA403, 0xA404, 0xA405, 0xA406, 0xA407, 0xA408, 0xA409, 0xA40A, 0xA40B, 0xA40C}),
    "maker":    ("Maker notes (private data from the camera brand)", set(), {0x927C}),
}
JPEG_ORDER = ["gps", "device", "datetime", "software", "person", "serial", "describe", "settings", "maker", "xmp", "iptc", "comment", "otherapp", "trailer"]
JPEG_LABEL = {"gps": "GPS location", "xmp": "XMP block (Adobe / editing history, creator tool)", "iptc": "IPTC block (caption, keywords, creator)",
              "comment": "JPEG comment text", "otherapp": "Other embedded blocks (APP segments, e.g. multi-picture or vendor data)",
              "trailer": "Extra data stored after the end of the image (phone trailers, hidden or motion-photo data)",
              **{k: v[0] for k, v in JPEG_EXIF.items()}}
EXIF_SIG = b"Exif\x00\x00"
XMP_SIG = b"http://ns.adobe.com/xap/1.0/"

def _is_exif(m, s): return m == 0xE1 and s[4:10] == EXIF_SIG
def _is_xmp(m, s): return m == 0xE1 and s[4:4 + len(XMP_SIG)] == XMP_SIG
def _is_icc(m, s): return m == 0xE2 and s[4:16] == b"ICC_PROFILE\x00"
def _is_other(m, s):
    if m == 0xE2 and not _is_icc(m, s): return True
    if 0xE3 <= m <= 0xEC or m == 0xEF: return True
    return m == 0xE1 and not _is_exif(m, s) and not _is_xmp(m, s)

def _exif(path):
    with Image.open(path) as im:
        ex = im.getexif()
        ex.get_ifd(0x8769)
        return ex

def _short(v, n=60):
    if isinstance(v, bytes): return f"<{len(v)} bytes>"
    s = str(v).strip("\x00 ")
    return s if len(s) <= n else s[:n] + "..."

def jpeg_items(path):
    data = open(path, "rb").read()
    segs, tail = T.jpeg_split(data)
    ex = _exif(path)
    sub = ex.get_ifd(0x8769)
    found, other_total = {}, 0
    gps = ex.get_ifd(0x8825)
    if gps:
        try:
            from .exifutil import _dms
            pos = f"{_dms(gps[2], gps.get(1)):.5f}, {_dms(gps[4], gps.get(3)):.5f}"
        except Exception: pos = "location data present"
        found["gps"] = pos
    for key, (_, t0, t1) in JPEG_EXIF.items():
        vals = [ex[t] for t in t0 if t in ex] + [sub[t] for t in t1 if t in sub]
        if vals:
            found[key] = _short(" ".join(_short(v, 30) for v in vals[:3])) + (f"  (+{len(vals) - 3} more)" if len(vals) > 3 else "")
    for m, s in segs:
        if _is_xmp(m, s): found["xmp"] = f"{len(s)} bytes"
        elif m == 0xED: found["iptc"] = f"{len(s)} bytes"
        elif m == 0xFE: found["comment"] = _short(s[4:].decode("utf-8", "ignore"))
        elif _is_other(m, s): other_total += len(s)
    if other_total: found["otherapp"] = f"{other_total} bytes"
    eoi = tail.find(b"\xff\xd9")
    if eoi >= 0 and len(tail) - (eoi + 2) > 0: found["trailer"] = f"{len(tail) - eoi - 2} bytes"
    return [{"key": k, "label": JPEG_LABEL[k], "detail": found[k]} for k in JPEG_ORDER if k in found]

def jpeg_remove(src, dst, keys: set):
    data = open(src, "rb").read()
    segs, tail = T.jpeg_split(data)
    ex = _exif(src)
    orientation = ex.get(0x0112)
    sub = ex.get_ifd(0x8769)
    exif_change = False
    if "gps" in keys and 0x8825 in ex:
        del ex[0x8825]; ex._ifds.pop(0x8825, None); exif_change = True
    for key, (_, t0, t1) in JPEG_EXIF.items():
        if key not in keys: continue
        for t in t0:
            if t in ex: del ex[t]; exif_change = True
        for t in t1:
            if t in sub: del sub[t]; exif_change = True
    if "trailer" in keys:
        e = tail.find(b"\xff\xd9")
        if e >= 0: tail = tail[:e + 2]
    keep, new_exif = [], None
    for m, s in segs:
        if _is_exif(m, s):
            if exif_change: new_exif = True
            else: keep.append((m, s))
            continue
        if (_is_xmp(m, s) and "xmp" in keys) or (m == 0xED and "iptc" in keys) or (m == 0xFE and "comment" in keys) or (_is_other(m, s) and "otherapp" in keys):
            continue
        keep.append((m, s))
    payload = None
    if new_exif:
        if orientation: ex[0x0112] = orientation
        payload = T._app1(ex.tobytes())
    open(dst, "wb").write(T._join(keep, tail, payload))

# ---- PNG
def png_chunks(path):
    d = open(path, "rb").read()
    if d[:8] != b"\x89PNG\r\n\x1a\n": raise T.ToolError("This is not a valid PNG file")
    i, out = 8, []
    while i + 12 <= len(d):
        ln = int.from_bytes(d[i:i + 4], "big"); typ = d[i + 4:i + 8]; out.append((typ, d[i:i + 12 + ln])); i += 12 + ln
        if typ == b"IEND": break
    return out

def _png_group(typ, chunk):
    if typ in (b"tEXt", b"zTXt", b"iTXt"): return "xmp" if b"XML:com.adobe.xmp" in chunk[8:40] else "text"
    return {b"eXIf": "exif", b"tIME": "time"}.get(typ)

PNG_LABEL = {"text": "Text notes (author, software, description)", "xmp": "XMP block", "exif": "EXIF block (camera, date, GPS)", "time": "Last-modified time stamp"}

def png_items(path):
    n = {}
    for typ, ch in png_chunks(path):
        g = _png_group(typ, ch)
        if g: n[g] = n.get(g, 0) + len(ch)
    return [{"key": k, "label": PNG_LABEL[k], "detail": f"{n[k]} bytes"} for k in ("exif", "text", "xmp", "time") if k in n]

def png_remove(src, dst, keys):
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    for typ, ch in png_chunks(src):
        if _png_group(typ, ch) not in keys: out += ch
    open(dst, "wb").write(bytes(out))

# ---- PDF
PDF_FIELDS = ["Title", "Author", "Subject", "Keywords", "Creator", "Producer", "CreationDate", "ModDate"]

def pdf_items(path):
    from pypdf import PdfReader
    r = PdfReader(path); m = r.metadata or {}; out = []
    for k in PDF_FIELDS:
        v = m.get("/" + k)
        if v: out.append({"key": "f:" + k, "label": {"CreationDate": "Created date", "ModDate": "Modified date"}.get(k, k), "detail": _short(v)})
    try:
        if "/Metadata" in r.trailer["/Root"]: out.append({"key": "xmp", "label": "XMP metadata block", "detail": "present"})
    except Exception: pass
    return out

def pdf_remove(src, dst, keys):
    from pypdf import PdfReader, PdfWriter
    r = PdfReader(src)
    if r.is_encrypted: raise T.ToolError("Encrypted PDF files are not supported")
    meta = {str(k): str(v) for k, v in (r.metadata or {}).items() if ("f:" + str(k).lstrip("/")) not in keys}
    w = PdfWriter(clone_from=src)
    w.metadata = None
    if meta: w.add_metadata(meta)
    if "xmp" in keys:
        try: del w._root_object["/Metadata"]
        except Exception: pass
    with open(dst, "wb") as f: w.write(f)

# ---- Office
def office_items(path):
    from .metadata import office_xml_meta
    out = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "docProps/core.xml" in names:
            root = ET.fromstring(z.read("docProps/core.xml"))
            lab = {"title": "Title", "creator": "Author", "lastModifiedBy": "Last modified by", "subject": "Subject", "keywords": "Keywords", "description": "Comments", "category": "Category"}
            for k, t in T.CORE_TAG.items():
                el = root.find(T._q(t))
                if el is not None and el.text and el.text.strip(): out.append({"key": "core:" + k, "label": lab[k], "detail": _short(el.text)})
        if "docProps/app.xml" in names:
            root = ET.fromstring(z.read("docProps/app.xml"))
            vals = [(el.tag.split("}")[1], el.text) for el in root if el.tag.split("}")[1] in ("Company", "Manager") and el.text and el.text.strip()]
            if vals: out.append({"key": "app", "label": "Company and manager", "detail": ", ".join(f"{a}: {_short(b, 30)}" for a, b in vals)})
        if "docProps/custom.xml" in names:
            root = ET.fromstring(z.read("docProps/custom.xml"))
            if len(root): out.append({"key": "custom", "label": "Custom properties", "detail": f"{len(root)} items"})
    return out

def office_remove(src, dst, keys):
    core = {k.split(":", 1)[1]: "" for k in keys if k.startswith("core:")}
    T._office_rewrite(src, dst, core, "app" in keys, "custom" in keys)

# ---- audio / video
def media_items(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_chapters", path], capture_output=True, text=True, timeout=120)
    j = json.loads(r.stdout or "{}")
    out = [{"key": "tag:" + k, "label": k, "detail": _short(v)} for k, v in (j.get("format", {}).get("tags") or {}).items() if str(v).strip()]
    if j.get("chapters"): out.append({"key": "chapters", "label": "Chapters", "detail": f"{len(j['chapters'])} chapters"})
    return out

def media_remove(src, dst, keys):
    args = ["-i", src, "-map", "0:v?", "-map", "0:a?", "-map", "0:s?", "-map_metadata", "0", "-c", "copy"]
    args += ["-map_chapters", "-1" if "chapters" in keys else "0"]
    for k in keys:
        if k.startswith("tag:"): args += ["-metadata", k[4:] + "="]
    T._ffmpeg(args + [dst])

# ---- public
KIND_NOTES = {
    "jpeg": ["Orientation is always kept so the photo stays upright.", "The picture itself is not re-encoded. Colour profile is kept."],
    "png": ["The picture itself is not re-encoded."],
    "pdf": ["Page content is not changed."], "office": ["Document content is not changed."],
    "media": ["Streams are copied without re-encoding."], "image_other": ["This format is cleaned as a whole (lossless re-save)."],
}

def items(path, kind):
    if kind == "jpeg": return jpeg_items(path)
    if kind == "png": return png_items(path)
    if kind == "pdf": return pdf_items(path)
    if kind == "office": return office_items(path)
    if kind == "media": return media_items(path)
    if kind == "image_other": return [{"key": "all", "label": "All embedded metadata", "detail": "lossless re-save"}]
    return []

def remove(src, directory, kind, ext, keys):
    avail = items(src, kind)
    have = {i["key"] for i in avail}
    keys = {k for k in keys if k in have}
    if not keys: raise T.ToolError("Select at least one item to remove")
    labels = {i["key"]: i["label"] for i in avail}
    if keys == have:  # everything chosen: use the full stripper
        dst, note = T.remove(src, directory, kind, ext)
        return dst, "All metadata removed. " + note
    dst = T._out_path(directory, ext, kind == "media")
    try:
        {"jpeg": jpeg_remove, "png": png_remove, "pdf": pdf_remove, "office": office_remove, "media": media_remove}[kind](src, dst, keys)
    except T.ToolError:
        if os.path.exists(dst): os.remove(dst)
        raise
    except Exception:
        if os.path.exists(dst): os.remove(dst)
        raise T.ToolError("This file could not be processed. It may be damaged or unsupported.")
    left = [k for k in labels if k not in keys]
    return dst, "Removed: " + ", ".join(labels[k] for k in labels if k in keys) + ". Kept: " + (", ".join(labels[k] for k in left) or "nothing")
