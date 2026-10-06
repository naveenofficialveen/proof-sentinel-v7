"""Forensic checks. They read only what is stored in the file and every result is an INDICATOR, not proof.
Nothing here changes the file. Each check is wrapped so one failure never hides the others."""
import hashlib, math, os, re
from datetime import datetime, timezone

# ---------------------------------------------------------------- JPEG structure (used by 1, 8, 6)
ZIGZAG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
          35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]
STD_LUM = [16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
           18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92, 49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99]
STD_CHR = [17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99, 24, 26, 56, 99, 99, 99, 99, 99, 47, 66, 99, 99, 99, 99, 99, 99] + [99] * 32
MARKER_NAMES = {0xD8: "SOI", 0xD9: "EOI", 0xDA: "SOS", 0xDB: "DQT", 0xC4: "DHT", 0xDD: "DRI", 0xFE: "COM", 0xC0: "SOF0 (baseline)",
                0xC1: "SOF1 (extended)", 0xC2: "SOF2 (progressive)", 0xDC: "DNL", 0xCC: "DAC"}
for _i in range(16): MARKER_NAMES[0xE0 + _i] = f"APP{_i}"
SW_TAGS = [b"Photoshop", b"Adobe", b"GIMP", b"Lavc", b"Facebook", b"WhatsApp", b"Instagram", b"Telegram", b"Google", b"Samsung", b"Apple",
           b"Snapseed", b"Picasa", b"Paint.NET", b"Canva", b"Lightroom", b"ImageMagick", b"libjpeg", b"FFmpeg", b"Created with"]
SOCIAL_SOURCES = ("whatsapp", "facebook", "instagram", "telegram", "messenger", "signal", "snapchat", "viber", "tiktok")

def _read(path, cap=64 * 1024 * 1024):
    with open(path, "rb") as f: return f.read(cap)

def jpeg_segments(data: bytes):
    """Header segments up to and including SOS, plus the offset where the compressed image data begins."""
    segs, i = [], 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        m = data[i + 1]
        if m == 0xFF: i += 1; continue
        if m == 0xD9: break
        if m == 0x01 or 0xD0 <= m <= 0xD7:
            segs.append({"m": m, "off": i, "len": 2, "data": b""}); i += 2; continue
        ln = int.from_bytes(data[i + 2:i + 4], "big")
        segs.append({"m": m, "off": i, "len": ln + 2, "data": data[i + 4:i + 2 + ln]}); i += 2 + ln
        if m == 0xDA: break
    return segs, i

def _printable(b: bytes, n=40):
    return "".join(chr(c) if 32 <= c < 127 else "." for c in b[:n]).strip(".")

def _tables(segs):
    out = {}
    for s in segs:
        if s["m"] != 0xDB: continue
        p, pos = s["data"], 0
        while pos < len(p):
            pq, tq = p[pos] >> 4, p[pos] & 15; pos += 1
            size = 128 if pq else 64
            raw = p[pos:pos + size]; pos += size
            if pq or len(raw) < 64: continue  # 16-bit tables are rare; skipped
            nat = [0] * 64
            for k, v in enumerate(raw[:64]): nat[ZIGZAG[k]] = v
            out[tq] = nat
    return out

def _ijg(std, q):
    s = 5000 // q if q < 50 else 200 - 2 * q
    return [min(255, max(1, (v * s + 50) // 100)) for v in std]

def ijg_quality(table, std):
    best = (None, 10 ** 9)
    for q in range(1, 101):
        d = sum(abs(a - b) for a, b in zip(table, _ijg(std, q)))
        if d < best[1]: best = (q, d)
        if d == 0: break
    return best

def _subsampling(segs):
    for s in segs:
        if s["m"] in (0xC0, 0xC1, 0xC2) and len(s["data"]) >= 9:
            n = s["data"][5]
            if n == 1: return "grayscale"
            hv = s["data"][7]
            return {0x22: "4:2:0", 0x21: "4:2:2", 0x11: "4:4:4", 0x12: "4:4:0", 0x41: "4:1:1"}.get(hv, f"{hv >> 4}x{hv & 15}")
    return None

def jpeg_scan(path):
    """Returns (dqt, hex). dqt = quantisation-table fingerprint, hex = marker list, software strings, trailing bytes."""
    data = _read(path)
    if data[:2] != b"\xff\xd8": return None, None
    segs, scan = jpeg_segments(data)
    tabs = _tables(segs)
    dqt = {"tables": len(tabs), "subsampling": _subsampling(segs),
           "progressive": any(s["m"] == 0xC2 for s in segs)}
    if 0 in tabs:
        q, d = ijg_quality(tabs[0], STD_LUM)
        exact = d == 0
        dqt.update({"luma_fingerprint": hashlib.sha1(bytes(tabs[0])).hexdigest()[:12], "ijg_quality": q, "exact": exact, "table_distance": d,
                    "luma_first_row": tabs[0][:8]})
        if 1 in tabs: dqt["chroma_matches_standard"] = ijg_quality(tabs[1], STD_CHR)[1] == 0 if exact else None
        if exact and q >= 90:
            dqt["classification"] = f"Standard libjpeg table, quality about {q}. High quality: typical of a first-generation save or export."
            dqt["social_hint"] = "low"
        elif exact and 55 <= q <= 89:
            dqt["classification"] = (f"Standard libjpeg table, quality about {q}. WhatsApp, Facebook, Instagram and many editors re-encode photos at roughly this level, "
                                     "so this looks like a re-compressed copy. The table alone cannot tell which app did it.")
            dqt["social_hint"] = "high"
        elif exact:
            dqt["classification"] = f"Standard libjpeg table, quality about {q}. Heavy compression, typical of repeated sharing."
            dqt["social_hint"] = "high"
        else:
            dqt["classification"] = ("Custom (non-standard) quantisation tables. Phone and camera firmware, Photoshop and some apps use their own tables, "
                                     "so this is more typical of a camera original or professional software than of a messaging app.")
            dqt["social_hint"] = "low"
    else:
        dqt["classification"] = "No luminance table could be read."
    # hex marker list
    rows = []
    for s in segs[:70]:
        name = MARKER_NAMES.get(s["m"], f"0x{s['m']:02X}")
        info = ""
        if 0xE0 <= s["m"] <= 0xEF: info = _printable(s["data"][:32])
        elif s["m"] == 0xFE: info = _printable(s["data"], 60)
        elif s["m"] == 0xDB: info = f"{len(s['data'])} bytes of table data"
        rows.append({"offset": f"0x{s['off']:04X}", "marker": name, "length": s["len"], "info": info})
    eoi = data.find(b"\xff\xd9", scan)
    trailing = len(data) - (eoi + 2) if eoi >= 0 else None
    full = len(data) < 64 * 1024 * 1024
    found = []
    low = data.lower()
    for t in SW_TAGS:
        c = low.count(t.lower())
        if c: found.append({"text": t.decode(), "count": c, "first_offset": f"0x{low.find(t.lower()):X}"})
    coms = [_printable(s["data"], 120) for s in segs if s["m"] == 0xFE]
    hx = {"header_hex": " ".join(f"{b:02X}" for b in data[:16]), "markers": rows, "eoi_offset": f"0x{eoi:X}" if eoi >= 0 else "not found",
          "trailing_bytes": trailing, "software_strings": found, "comments": coms, "complete_scan": full}
    return dqt, hx

def png_scan(path):
    d = _read(path, 8 * 1024 * 1024)
    if d[:8] != b"\x89PNG\r\n\x1a\n": return None
    rows, i = [], 8
    while i + 12 <= len(d) and len(rows) < 70:
        ln = int.from_bytes(d[i:i + 4], "big"); typ = d[i + 4:i + 8].decode("latin-1")
        rows.append({"offset": f"0x{i:04X}", "marker": typ, "length": ln + 12, "info": _printable(d[i + 8:i + 8 + min(ln, 40)]) if typ in ("tEXt", "iTXt", "zTXt") else ""})
        i += 12 + ln
        if typ == "IEND": break
    low = d.lower()
    found = [{"text": t.decode(), "count": low.count(t.lower()), "first_offset": f"0x{low.find(t.lower()):X}"} for t in SW_TAGS if low.count(t.lower())]
    return {"header_hex": " ".join(f"{b:02X}" for b in d[:16]), "markers": rows, "software_strings": found, "comments": [], "trailing_bytes": None}

# ---------------------------------------------------------------- 2. magic bytes
EXT_OK = {"jpg": {"jpeg"}, "jpeg": {"jpeg"}, "png": {"png"}, "gif": {"gif"}, "webp": {"webp"}, "bmp": {"bmp"}, "tif": {"tiff"}, "tiff": {"tiff"},
          "pdf": {"pdf"}, "zip": {"zip"}, "docx": {"zip"}, "xlsx": {"zip"}, "pptx": {"zip"}, "doc": {"ole"}, "xls": {"ole"}, "ppt": {"ole"},
          "7z": {"7z"}, "rar": {"rar"}, "gz": {"gz"}, "mp4": {"mp4"}, "mov": {"mp4"}, "m4a": {"mp4"}, "avi": {"avi"}, "mkv": {"ebml"}, "webm": {"ebml"},
          "mp3": {"mp3"}, "aac": {"mp3"}, "wav": {"wav"}, "flac": {"flac"}, "ogg": {"ogg"}, "mpeg": {"mpeg"}, "mpg": {"mpeg"},
          "txt": {"text", "script_text"}, "csv": {"text", "script_text"}}
EXEC_EXT = {"exe", "dll", "com", "scr", "sys", "bin", "so", "elf", "o", "dylib", "app", "msi"}
KIND_NAME = {"jpeg": "JPEG image", "png": "PNG image", "gif": "GIF image", "pdf": "PDF document", "zip": "ZIP container (also DOCX, XLSX, PPTX)",
             "ole": "Legacy Office document (DOC, XLS, PPT)", "7z": "7-Zip archive", "rar": "RAR archive", "gz": "GZIP archive", "bmp": "BMP image",
             "tiff": "TIFF image", "webp": "WebP image", "wav": "WAV audio", "avi": "AVI video", "mp4": "MP4 / QuickTime family", "ebml": "Matroska / WebM video",
             "mp3": "MP3 / AAC audio", "ogg": "Ogg media", "flac": "FLAC audio", "mpeg": "MPEG video", "exe": "Windows executable program",
             "elf": "Linux executable program", "macho": "macOS / Java executable", "script_text": "Script or web page (text)", "text": "Plain text"}

def sniff(h: bytes) -> str | None:
    if h.startswith(b"\xff\xd8\xff"): return "jpeg"
    if h.startswith(b"\x89PNG\r\n\x1a\n"): return "png"
    if h[:4] == b"GIF8": return "gif"
    if h.startswith(b"%PDF-"): return "pdf"
    if h[:4] in (b"PK\x03\x04", b"PK\x05\x06"): return "zip"
    if h.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"): return "ole"
    if h.startswith(b"7z\xbc\xaf\x27\x1c"): return "7z"
    if h.startswith(b"Rar!\x1a\x07"): return "rar"
    if h[:2] == b"\x1f\x8b": return "gz"
    if h[:2] == b"BM" and h[6:10] == b"\x00\x00\x00\x00": return "bmp"
    if h[:4] in (b"II*\x00", b"MM\x00*"): return "tiff"
    if h[:4] == b"RIFF":
        return {b"WEBP": "webp", b"WAVE": "wav", b"AVI ": "avi"}.get(h[8:12])
    if h[4:8] == b"ftyp": return "mp4"
    if h[:4] == b"\x1a\x45\xdf\xa3": return "ebml"
    if h[:3] == b"ID3" or (len(h) > 1 and h[0] == 0xFF and (h[1] & 0xE0) == 0xE0): return "mp3"
    if h[:4] == b"OggS": return "ogg"
    if h[:4] == b"fLaC": return "flac"
    if h[:2] == b"MZ": return "exe"
    if h[:4] == b"\x7fELF": return "elf"
    if h[:4] in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe"): return "macho"
    if h[:3] == b"\x00\x00\x01" and len(h) > 3 and h[3] in (0xBA, 0xB3): return "mpeg"
    if b"\x00" not in h[:4096] and h:
        try: txt = h[:4096].decode("utf-8", "ignore")
        except Exception: return None
        if sum(c.isprintable() or c in "\r\n\t" for c in txt) / max(1, len(txt)) > 0.95:
            low = h[:512].lstrip().lower()
            return "script_text" if low.startswith((b"#!", b"<?php", b"<script", b"<%", b"<html", b"<!doctype html")) else "text"
    return None

def magic_check(head: bytes, filename: str) -> dict:
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    kind = sniff(head)
    dangerous = kind in ("exe", "elf", "macho", "script_text")
    ok = None if ext not in EXT_OK else (kind in EXT_OK[ext])
    blocked = (kind in ("exe", "elf", "macho") and ext not in EXEC_EXT) or (kind == "script_text" and ext in EXT_OK and ext not in ("txt", "csv"))
    if blocked: verdict, msg = "DANGEROUS", f"The name says .{ext or '?'} but the first bytes are {KIND_NAME[kind].lower()}. This is a disguised program or script."
    elif kind in ("exe", "elf", "macho"): verdict, msg = "EXECUTABLE", "This is a real executable program. It is stored and analysed only; it is never run."
    elif ok is False: verdict, msg = "MISMATCH", f"The name says .{ext} but the content is {KIND_NAME.get(kind, 'something else').lower()}. The file may have been renamed."
    elif ok is None: verdict, msg = "NO RULE", "No signature rule exists for this extension, so only the detected type is reported."
    else: verdict, msg = "OK", "The first bytes match what the file name claims."
    parts = filename.lower().rsplit(".", 2)
    dbl = len(parts) == 3 and parts[1] in {"jpg", "jpeg", "png", "pdf", "doc", "docx", "xls", "xlsx", "txt", "gif", "mp4", "zip"} and len(parts[2]) <= 4
    return {"extension": ext or "none", "header_hex": " ".join(f"{b:02X}" for b in head[:16]), "detected_type": KIND_NAME.get(kind, "Unknown binary data" if kind is None else kind),
            "verdict": verdict, "message": msg, "blocked": blocked, "double_extension": bool(dbl)}

# ---------------------------------------------------------------- 3. ELA heat-map
def _ela_arrays(path, quality=90, max_pixels=20_000_000):
    import cv2, numpy as np
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None: return None
    h, w = img.shape[:2]; scaled = False
    if h * w > max_pixels:
        s = math.sqrt(max_pixels / (h * w)); img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA); scaled = True
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    again = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    diff = cv2.absdiff(img, again).max(axis=2).astype(np.float32)
    return img, diff, scaled

def ela_stats(path):
    """Return a conservative ELA indicator.

    ELA is content-dependent: natural edges and prior JPEG re-saves can create
    bright areas. We therefore flag compact block outliers relative to the
    image's own median/MAD baseline instead of treating every hot block as an edit.
    """
    import numpy as np
    r = _ela_arrays(path)
    if r is None: return None
    img, diff, scaled = r
    h, w = diff.shape
    bh, bw = h // 16, w // 16
    if bh < 2 or bw < 2:
        return {"verdict": "Image too small for a meaningful ELA", "level": "n/a",
                "mean_error": round(float(diff.mean()), 2), "peak_error": round(float(np.percentile(diff, 99.5)), 1),
                "hot_area_percent": 0.0, "hot_region": None, "analysed_downscaled": scaled}

    blocks = diff[:bh * 16, :bw * 16].reshape(bh, 16, bw, 16).mean(axis=(1, 3))
    med = float(np.median(blocks))
    mad = float(np.median(np.abs(blocks - med)) * 1.4826) + 1e-3
    # Must be both statistically unusual and materially above the image baseline.
    hot = (blocks > np.maximum(med * 2.2 + 0.5, 3.0)) & (((blocks - med) / mad) > 4.0)
    frac = float(hot.mean())

    bbox = None
    if hot.any():
        # Connected components keep isolated natural edges from becoming one giant region.
        import cv2
        mask = (hot.astype(np.uint8) * 255)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        candidates = []
        for i in range(1, n):
            x, y, ww, hh, area = stats[i]
            if area < 1: continue
            candidates.append((area, x, y, ww, hh))
        candidates.sort(reverse=True)
        if candidates:
            area, x, y, ww, hh = candidates[0]
            # Ignore tiny isolated blocks (< 1% of image area).
            if (ww * 16) * (hh * 16) >= 0.01 * w * h:
                bbox = {"x": round(100 * x / bw, 1), "y": round(100 * y / bh, 1),
                        "w": round(100 * ww / bw, 1), "h": round(100 * hh / bh, 1)}

    # Spread over a large portion usually means texture/re-save noise, not one edit.
    inconclusive = frac > 0.08
    if inconclusive:
        level, verdict = "medium", "Large parts of the picture differ. This is more consistent with re-saving or textured content than one localized edit."
        bbox = None
    elif bbox:
        level, verdict = "high", "A compact region reacts differently from the rest. This can mean a region was pasted, retouched or morphed. Check the red area by eye."
    else:
        level, verdict = "low", "No compact block stands out from the image's own compression baseline."

    return {"mean_error": round(float(diff.mean()), 2), "peak_error": round(float(np.percentile(diff, 99.5)), 1),
            "hot_area_percent": round(frac * 100, 2), "hot_region": bbox, "level": level,
            "verdict": verdict, "analysed_downscaled": scaled}

def _fit(img, max_side):
    import cv2
    h, w = img.shape[:2]
    if max(h, w) > max_side:
        k = max_side / max(h, w); img = cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
    return img

def ela_layer_png(path, out_path, max_side=1400):
    """Transparent PNG: red where the error level is unusually high. Shown on top of the preview picture."""
    import cv2, numpy as np
    r = _ela_arrays(path)
    if r is None: raise ValueError("not an image")
    img, diff, _ = r
    heat = cv2.GaussianBlur(diff, (0, 0), 6)
    a = np.clip(heat / max(float(np.percentile(heat, 99.5)), 1.0), 0, 1) ** 1.6
    layer = np.zeros((*a.shape, 4), np.uint8); layer[:, :, 2] = 255; layer[:, :, 3] = (a * 200).astype(np.uint8)
    layer = _fit(layer, max_side)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, layer)

def preview_jpg(path, out_path, max_side=1400):
    import cv2
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None: raise ValueError("not an image")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, _fit(img, max_side), [cv2.IMWRITE_JPEG_QUALITY, 85])

# ---------------------------------------------------------------- 4. OCR hash lock
STOP_WORDS = {"ID", "DOB", "AGE", "SEX", "GENDER", "FATHER", "MOTHER", "ADDRESS", "NO", "NUMBER", "DATE", "AADHAAR", "AADHAR", "PAN", "PASSPORT", "CARD", "BIRTH", "SIGNATURE"}
ID_PATTERNS = [r"\b[A-Z]{5}\d{4}[A-Z]\b", r"\b\d{4}\s?\d{4}\s?\d{4}\b", r"\b[A-Z]{1,4}\d{4,12}\b"]

def doc_lock(text):
    if not text or len(text.strip()) < 8:
        return {"status": "not_applicable", "reason": "No readable OCR text was found."}
    norm = re.sub(r"\s+", " ", text).strip().upper()
    ids = sorted({re.sub(r"\s", "", m) for p in ID_PATTERNS for m in re.findall(p, norm)})[:12]
    nums = sorted(set(re.findall(r"\d+", norm)))
    nm = re.search(r"NAME\s*[:\-]?\s*((?:[A-Z][A-Z.]+\s?){1,6})", norm)
    name = None
    if nm:
        words = []
        for w in nm.group(1).split():
            if w in STOP_WORDS: break
            words.append(w)
        name = " ".join(words[:4]) or None
    return {"status": "locked", "ids": ids, "number_count": len(nums), "name_guess": name, "characters": len(norm),
            "fields_sha256": hashlib.sha256("|".join(ids + nums).encode()).hexdigest(), "text_sha256": hashlib.sha256(norm.encode()).hexdigest()}

# ---------------------------------------------------------------- 6. location + privacy
def geo_of(spec):
    m = re.match(r"^\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\s*$", str(spec.get("GPS position", "")))
    if not m: return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if abs(lat) > 90 or abs(lon) > 180: return None
    return {"lat": lat, "lon": lon, "altitude": spec.get("GPS altitude")}

def privacy(spec):
    has = lambda *ks: any(k in spec for k in ks)
    rows = [("GPS location", 40, spec.get("GPS present") == "Yes"), ("Device make, model or lens", 15, has("Make", "Model", "LensModel")),
            ("Date and time taken", 10, has("DateTimeOriginal", "DateTime", "DateTimeDigitized")),
            ("Person: author, owner or copyright", 15, has("Artist", "Copyright", "CameraOwnerName", "XMP creator", "XMP rights", "IPTC Creator", "IPTC Copyright")),
            ("Serial or unique ID numbers", 10, has("BodySerialNumber", "LensSerialNumber", "ImageUniqueID")),
            ("Software and extra XMP / IPTC blocks", 10, has("Software", "XMP CreatorTool") or any(k.startswith(("XMP ", "IPTC ")) for k in spec))]
    score = 100 - sum(p for _, p, on in rows if on)
    return {"score": score, "level": "Good" if score >= 80 else "Moderate" if score >= 50 else "Exposed",
            "items": [{"item": n, "points": p, "present": bool(on)} for n, p, on in rows]}

# ---------------------------------------------------------------- 7. Laplacian gauge
def sharpness(path, ijg_q=None, exact=False):
    import cv2
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if g is None: return None
    h, w = g.shape
    if max(h, w) > 1024:
        s = 1024 / max(h, w); g = cv2.resize(g, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    var = float(cv2.Laplacian(g, cv2.CV_64F).var())
    score = 100 * min(1.0, math.log10(1 + var) / math.log10(1 + 800))
    if exact and ijg_q and ijg_q < 85: score -= (85 - ijg_q) * 0.6
    score = int(max(0, min(100, round(score))))
    heavy = bool(exact and ijg_q is not None and ijg_q < 90)  # "forwarded" is only claimed when the JPEG tables also show heavy compression
    if score >= 70: label, tone = "Original Camera Sharp Capture (High Quality)", "ok"
    elif score >= 40 or not heavy: label, tone = "Compressed or Shared Once or Twice (Medium Quality)", "warn"
    else: label, tone = "Multiple Times Forwarded File (Low Quality Risk)", "bad"
    return {"score": score, "label": label, "tone": tone, "laplacian_variance": round(var, 1), "jpeg_quality": ijg_q if exact else None,
            "note": "Sharpness also depends on the scene: a plain wall or a night photo can score low without being forwarded."}

# ---------------------------------------------------------------- 9. size vs camera sensors
SENSORS = {(4032, 3024): "12 MP phone (iPhone, many Android)", (4000, 3000): "12 MP phone (Samsung and others)", (4608, 3456): "16 MP phone",
           (4624, 3472): "16 MP phone (Samsung)", (3264, 2448): "8 MP phone", (2592, 1944): "5 MP phone", (2048, 1536): "3 MP phone", (1600, 1200): "2 MP camera",
           (4160, 3120): "13 MP phone", (4128, 3096): "13 MP phone", (5120, 3840): "20 MP phone", (5184, 3880): "20 MP phone", (5344, 4016): "21 MP phone",
           (5712, 4284): "24 MP phone", (6016, 4512): "27 MP phone", (7680, 5760): "44 MP phone", (8000, 6000): "48 MP phone",
           (8064, 6048): "48 MP phone (iPhone)", (8160, 6120): "50 MP phone (Pixel and others)", (9248, 6936): "64 MP phone", (9280, 6944): "64 MP phone",
           (12000, 9000): "108 MP phone", (4032, 2268): "16:9 phone photo", (4000, 2250): "16:9 phone photo", (3840, 2160): "4K frame / 16:9 photo",
           (4608, 2592): "16:9 phone photo", (3264, 1836): "16:9 phone photo", (1920, 1080): "Full HD frame / 16:9 photo", (3024, 3024): "Square 12 MP photo",
           (4000, 4000): "Square photo", (6000, 4000): "24 MP DSLR / mirrorless", (6240, 4160): "26 MP DSLR", (5472, 3648): "20 MP DSLR (Canon)",
           (5616, 3744): "21 MP DSLR (Canon)", (6720, 4480): "30 MP DSLR (Canon)", (7360, 4912): "36 MP DSLR (Nikon)", (8256, 5504): "45 MP DSLR",
           (4928, 3264): "16 MP DSLR", (4288, 2848): "12 MP DSLR (Nikon)", (5184, 3456): "18 MP DSLR (Canon)", (4272, 2848): "12 MP DSLR (Canon)",
           (3872, 2592): "10 MP DSLR", (3000, 2000): "6 MP DSLR", (4000, 2672): "10 MP DSLR", (5760, 3840): "22 MP DSLR", (6048, 4024): "24 MP DSLR (Canon)"}
SOCIAL_LONG = {1600: "WhatsApp standard quality", 2048: "Facebook / high-quality share", 1080: "Instagram width", 1440: "Instagram / Facebook", 960: "Facebook small",
               1280: "WhatsApp / Telegram", 800: "WhatsApp small", 1350: "Instagram portrait"}
ASPECTS = {(4, 3): "4:3", (3, 2): "3:2", (16, 9): "16:9", (1, 1): "1:1", (5, 4): "5:4", (16, 10): "16:10", (2, 1): "2:1", (21, 9): "21:9"}

def size_check(spec):
    m = re.match(r"^(\d+)x(\d+)$", str(spec.get("Dimensions", "")))
    if not m: return None
    w, h = int(m.group(1)), int(m.group(2)); hi, lo = max(w, h), min(w, h)
    g = math.gcd(w, h); ratio = ASPECTS.get((w // g, h // g)) or ASPECTS.get((h // g, w // g)) or f"{w // g}:{h // g}"
    sensor = SENSORS.get((hi, lo))
    ex, ey = spec.get("ExifImageWidth"), spec.get("ExifImageHeight")
    exif_dims = None
    try: exif_dims = (max(int(ex), int(ey)), min(int(ex), int(ey))) if ex and ey else None
    except ValueError: pass
    has_cam = any(k in spec for k in ("Make", "Model"))
    reasons = []
    if exif_dims and exif_dims != (hi, lo): reasons.append(f"EXIF says {exif_dims[0]}x{exif_dims[1]} but the real size is {hi}x{lo}, so the picture was resized or cropped after it was taken.")
    if not sensor and not exif_dims: reasons.append("The size is not in the list of common phone and DSLR sensor sizes.")
    anomaly = bool(reasons)
    hint = SOCIAL_LONG.get(hi) if not sensor else None
    return {"width": w, "height": h, "megapixels": round(w * h / 1e6, 2), "aspect_ratio": ratio, "matches_sensor": sensor, "exif_dimensions": f"{exif_dims[0]}x{exif_dims[1]}" if exif_dims else None,
            "anomaly": anomaly, "has_camera_exif": has_cam, "social_size_hint": hint,
            "message": ("Size Anomaly: This image size does not match direct camera sensors; it is resized/cropped by an app. " + " ".join(reasons) +
                        " (The list covers common sizes, so a rare device can still be genuine.)") if anomaly else
                       ("Size matches " + (sensor or "the camera's own EXIF dimensions") + ". No resize sign.")}

# ---------------------------------------------------------------- 10. filename patterns
_D = r"(?P<y>\d{4})-?(?P<mo>\d\d)-?(?P<d>\d\d)"
_T = r"(?P<H>\d\d)[-._]?(?P<M>\d\d)[-._]?(?P<S>\d\d)"
FN = [
    (rf"^IMG-{_D}-WA\d{{4}}\.", "WhatsApp (Android): received photo", "social", None),
    (rf"^VID-{_D}-WA\d{{4}}\.", "WhatsApp (Android): received video", "social", None),
    (rf"^(AUD|PTT|DOC|STK)-{_D}-WA\d{{4}}\.", "WhatsApp (Android): audio, voice note, document or sticker", "social", None),
    (r"^WhatsApp (Image|Video|Audio|Document|Voice Message) (?P<y>\d{4})-(?P<mo>\d\d)-(?P<d>\d\d) at (?P<H>\d{1,2})\.(?P<M>\d\d)\.(?P<S>\d\d)", "WhatsApp (Web, Desktop or iOS export)", "social", None),
    (r"^FB_IMG_(?P<ts>\d{10,13})", "Facebook app download", "social", "The number is a Unix timestamp of the download."),
    (r"^received_\d{8,}", "Facebook Messenger received file", "social", None),
    (r"^\d{6,}_\d{6,}_\d{6,}_[nos]\.", "Facebook / Instagram web download (CDN name)", "social", None),
    (r"^Messenger_creation_", "Facebook Messenger created picture", "social", None),
    (rf"^photo_{_D}_(?P<H>\d\d)-(?P<M>\d\d)-(?P<S>\d\d)", "Telegram photo", "social", None),
    (rf"^(video|animation)_{_D}_(?P<H>\d\d)-(?P<M>\d\d)-(?P<S>\d\d)", "Telegram video or animation", "social", None),
    (r"^photo_\d+@(?P<d>\d\d)-(?P<mo>\d\d)-(?P<y>\d{4})_(?P<H>\d\d)-(?P<M>\d\d)-(?P<S>\d\d)", "Telegram Desktop", "social", None),
    (rf"^signal-{_D}-{_T}", "Signal", "social", None),
    (r"^Snapchat-\d+", "Snapchat", "social", None),
    (rf"^viber_image_{_D}_(?P<H>\d\d)-(?P<M>\d\d)-(?P<S>\d\d)", "Viber", "social", None),
    (r"^(tiktok|TikTok)", "TikTok", "social", None),
    (rf"^Screen ?[Ss]hot[_ ]{_D}[-_ ]?(at )?{_T}", "Screenshot (Android, Windows or macOS)", "screenshot", "Screenshots carry no camera data."),
    (r"^Screenshot \(\d+\)\.", "Screenshot (Windows)", "screenshot", "Screenshots carry no camera data."),
    (rf"^PXL_{_D}_{_T}", "Google Pixel camera", "camera", None),
    (rf"^WIN_{_D}_{_T}(?:_[A-Za-z0-9-]+)?\.", "Windows Camera app photo", "camera",
     "Windows Camera commonly uses WIN_YYYYMMDD_HH_MM_SS_... names."),
    (rf"^IMG{_D}{_T}\.", "Android camera (compact timestamp name)", "camera",
     "Some Android/OPPO camera apps save IMGYYYYMMDDHHMMSS.jpg without separators."),
    (rf"^(MVIMG|IMG|VID)_{_D}_{_T}", "Android camera (Google, Motorola, OnePlus, Xiaomi, Oppo and others)", "camera",
     "Instagram on Android saves with the same style, so check the folder the file came from."),
    (rf"^{_D}_{_T}(_\w+)?\.", "Samsung / Huawei / generic Android camera", "camera", None),
    (rf"^{_D}[ _-]{_T}\.", "Android gallery or Dropbox camera upload", "camera", None),
    (r"^IMG_E\d{4}\.", "Apple iPhone/iPad: edited copy", "camera", None),
    (r"^IMG_\d{4}\.", "Apple iPhone/iPad or Canon camera", "camera", None),
    (r"^_?DSC_?\d{4,5}\.", "Nikon or Sony camera", "camera", None), (r"^DSCN\d{4}\.", "Nikon Coolpix", "camera", None),
    (r"^_MG_\d{4}\.", "Canon camera (Adobe RGB)", "camera", None), (r"^P\d{7}\.", "Panasonic / Olympus camera", "camera", None),
    (r"^(GOPR|GP\d\d)\d{4}\.", "GoPro", "camera", None), (r"^DJI_\d{4}", "DJI drone or camera", "camera", None),
    (r"^(SAM|SDC)_?\d{4,5}\.", "Samsung digital camera", "camera", None), (r"^(PICT|HPIM|CIMG|IMAG)\d{4}\.", "Compact digital camera", "camera", None),
    (r"^(image|download|Capture|Untitled|Snip)( \(\d+\))?\.", "Generic name from a browser, snipping tool or editor", "generic", "The original name was lost, so no source can be read from it."),
]
FN_RX = [(re.compile(p, re.I if not p.startswith("^_") else 0), l, f, n) for p, l, f, n in FN]

def _fn_date(g):
    try:
        if g.get("ts"):
            t = int(g["ts"]); t = t / 1000 if t > 1e11 else t
            d = datetime.fromtimestamp(t, timezone.utc)
            return d.strftime("%Y-%m-%d %H:%M:%S UTC") if 2005 <= d.year <= 2100 else None
        y, mo, d = int(g["y"]), int(g["mo"]), int(g["d"]); datetime(y, mo, d)
        s = f"{y:04d}-{mo:02d}-{d:02d}"
        if g.get("H"): s += f" {int(g['H']):02d}:{int(g['M']):02d}:{int(g.get('S') or 0):02d}"
        return s
    except Exception:
        return None

def filename_check(name, exif_date=None):
    base = os.path.basename(name)
    out = {"name": base, "matched": False, "pattern": None, "family": None, "date": None, "notes": [], "flags": []}
    for rx, label, fam, note in FN_RX:
        m = rx.match(base)
        if m:
            out.update({"matched": True, "pattern": label, "family": fam, "date": _fn_date(m.groupdict())})
            if note: out["notes"].append(note)
            break
    if not out["matched"]: out["notes"].append("No known app or camera naming pattern. The file may have been renamed by its owner.")
    if re.search(r"\(\d+\)(\.\w+)?$|[ _-]Copy( \(\d+\))?(\.\w+)?$|^Copy of ", base, re.I): out["flags"].append("Copy marker in the name: the file was downloaded or copied more than once.")
    if re.search(r"\.(jpe?g|png|pdf|docx?|xlsx?|txt|gif|mp4|zip)\.[A-Za-z0-9]{2,4}$", base, re.I): out["flags"].append("Double extension: a classic trick to hide the real file type.")
    if out["date"] and exif_date:
        ed = str(exif_date)[:10].replace(":", "-")
        out["notes"].append("The date in the name matches the EXIF capture date." if out["date"][:10] == ed else
                            f"The date in the name ({out['date'][:10]}) is not the EXIF capture date ({ed}). Normal for forwarded or downloaded files.")
    return out

# ---------------------------------------------------------------- summary + entry point
def social_trace(spec, dqt, size, fname, hexi):
    score, why = 0, []
    if spec.get("Format") == "JPEG" and not any(k in spec for k in ("Make", "Model", "DateTimeOriginal")): score += 1; why.append("Camera metadata is missing, which apps remove when you share a photo.")
    if dqt and dqt.get("social_hint") == "high": score += 2; why.append(f"Quantisation table matches a re-compression at quality about {dqt.get('ijg_quality')}.")
    if size and size.get("social_size_hint"): score += 1; why.append(f"The long side ({max(size['width'], size['height'])} px) is a size used by: {size['social_size_hint']}.")
    src = None
    if fname and fname.get("family") == "social": score += 2; src = fname["pattern"]; why.append(f"The file name follows the {fname['pattern']} pattern.")
    marks = [s["text"] for s in (hexi or {}).get("software_strings", []) if s["text"].lower() in SOCIAL_SOURCES]
    if marks: score += 3; src = src or ", ".join(marks); why.append("The file contains these app names inside its code: " + ", ".join(marks) + ".")
    verdict = "Strong signs of social-media or messaging-app handling" if score >= 4 else "Possible re-share or re-compression" if score >= 2 else "No clear sign of social-media handling"
    return {"score": score, "verdict": verdict, "likely_source": src, "reasons": why,
            "note": "These are indicators. Several apps behave alike, and a file can be re-saved by hand."}

def _safe(fn, *a):
    try: return fn(*a)
    except Exception: return {"error": "This check could not run on this file"}

def compute(path, filename, info, specific, ocr_text=None):
    """Everything except the cross-file document-lock comparison (that needs the database, see forensics_db)."""
    specific = specific or {}
    out = {"version": 1}
    with open(path, "rb") as f: head = f.read(4096)
    out["magic"] = _safe(magic_check, head, filename)
    out["filename"] = _safe(filename_check, filename, specific.get("DateTimeOriginal"))
    if info.get("category") != "image": return out
    out["size_check"] = _safe(size_check, specific)
    dqt = hexi = None
    if info.get("mime") == "image/jpeg":
        try: dqt, hexi = jpeg_scan(path)
        except Exception: pass
        out["ela"] = _safe(ela_stats, path)
    elif info.get("mime") == "image/png":
        out["hex"] = _safe(png_scan, path)
    if dqt: out["dqt"] = dqt
    if hexi: out["hex"] = hexi
    out["quality"] = _safe(sharpness, path, (dqt or {}).get("ijg_quality"), bool((dqt or {}).get("exact")))
    out["privacy"] = _safe(privacy, specific)
    out["geo"] = geo_of(specific)
    out["social"] = _safe(social_trace, specific, dqt, out["size_check"] if "anomaly" in (out["size_check"] or {}) else None, out["filename"], out.get("hex"))
    out["doc_lock"] = doc_lock(ocr_text)
    return out
