"""Readable image metadata: EXIF (camera, lens, flash, exposure, GPS), IPTC, XMP, ICC, PNG text, JPEG comment.
Only reports what is actually stored in the file. One bad tag never hides the others."""
import io, math, re
from xml.etree import ElementTree as ET
from PIL import Image, ExifTags

EXIF_IFD, GPS_IFD, INTEROP_IFD = 0x8769, 0x8825, 0xA005
POINTERS = {EXIF_IFD, GPS_IFD, INTEROP_IFD}

LOOKUP = {
    "ExposureProgram": {0: "Not defined", 1: "Manual", 2: "Program AE", 3: "Aperture-priority AE", 4: "Shutter speed priority AE", 5: "Creative (slow speed)", 6: "Action (high speed)", 7: "Portrait", 8: "Landscape"},
    "MeteringMode": {0: "Unknown", 1: "Average", 2: "Center-weighted average", 3: "Spot", 4: "Multi-spot", 5: "Multi-segment", 6: "Partial", 255: "Other"},
    "WhiteBalance": {0: "Auto", 1: "Manual"},
    "ExposureMode": {0: "Auto", 1: "Manual", 2: "Auto bracket"},
    "LightSource": {0: "Unknown", 1: "Daylight", 2: "Fluorescent", 3: "Tungsten", 4: "Flash", 9: "Fine weather", 10: "Cloudy", 11: "Shade", 255: "Other"},
    "Orientation": {1: "Horizontal (normal)", 2: "Mirror horizontal", 3: "Rotate 180", 4: "Mirror vertical", 5: "Mirror horizontal, rotate 270 CW", 6: "Rotate 90 CW", 7: "Mirror horizontal, rotate 90 CW", 8: "Rotate 270 CW"},
    "SceneCaptureType": {0: "Standard", 1: "Landscape", 2: "Portrait", 3: "Night"},
    "ColorSpace": {1: "sRGB", 65535: "Uncalibrated"},
    "ResolutionUnit": {1: "None", 2: "inches", 3: "cm"},
    "YCbCrPositioning": {1: "Centered", 2: "Co-sited"},
    "SensingMethod": {1: "Not defined", 2: "One-chip color area", 3: "Two-chip color area", 4: "Three-chip color area", 5: "Color sequential area", 7: "Trilinear", 8: "Color sequential linear"},
    "GainControl": {0: "None", 1: "Low gain up", 2: "High gain up", 3: "Low gain down", 4: "High gain down"},
    "Contrast": {0: "Normal", 1: "Low", 2: "High"}, "Saturation": {0: "Normal", 1: "Low", 2: "High"}, "Sharpness": {0: "Normal", 1: "Soft", 2: "Hard"},
    "CustomRendered": {0: "Normal", 1: "Custom"},
}

def decode_flash(v: int) -> str:
    if v & 0x20:
        return "No flash function"
    mode = {1: "On", 2: "Off", 3: "Auto"}.get((v >> 3) & 3)
    parts = [p for p in (mode, "Fired" if v & 1 else "Did not fire") if p]
    ret = (v >> 1) & 3
    if ret == 2: parts.append("return light not detected")
    if ret == 3: parts.append("return light detected")
    if v & 0x40: parts.append("red-eye reduction")
    return ", ".join(parts)

def _rat(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None

def _fmt(name, v):
    if isinstance(v, bytes):
        if name in ("ExifVersion", "FlashpixVersion") and v.isascii():
            return v.decode()
        if name == "UserComment":
            return v[8:].decode("utf-8", "ignore").strip("\x00 ").strip() or None
        return f"<binary, {len(v)} B>"
    if name == "Flash" and isinstance(v, int):
        return decode_flash(v)
    if name in LOOKUP and isinstance(v, int):
        return LOOKUP[name].get(v, str(v))
    if name == "ExposureTime":
        f = _rat(v)
        if f:
            return f"1/{round(1 / f)}" if f < 1 else f"{f:g} s"
    if name == "FNumber":
        f = _rat(v); return f"f/{f:g}" if f else None
    if name in ("FocalLength", "FocalLengthIn35mmFilm"):
        f = _rat(v); return f"{f:g} mm" if f else None
    if name in ("ISOSpeedRatings", "PhotographicSensitivity"):
        return str(v[0] if isinstance(v, (tuple, list)) and v else v)
    if hasattr(v, "numerator"):
        f = _rat(v); return f"{f:g}" if f is not None else None
    if isinstance(v, (tuple, list)):
        return ", ".join(str(_rat(x) if hasattr(x, "numerator") else x) for x in v)
    if isinstance(v, str):
        return v.strip("\x00 ").strip() or None
    return str(v)

def _dms(vals, ref):
    d, m, s = (float(x) for x in vals)
    out = d + m / 60 + s / 3600
    return -out if ref in ("S", "W") else out

def _manual_exif(path):
    """Fallback: find the EXIF APP1 segment ourselves if Pillow could not read it."""
    data = open(path, "rb").read(3_000_000)
    i = 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        m = data[i + 1]
        if m in (0xD9, 0xDA): break
        if m == 0xFF: i += 1; continue
        ln = int.from_bytes(data[i + 2:i + 4], "big")
        seg = data[i + 4:i + 2 + ln]
        if m == 0xE1 and seg[:6] == b"Exif\x00\x00":
            ex = Image.Exif(); ex.load(seg); return ex
        i += 2 + ln
    return None

XMP_KEYS = {"CreatorTool", "Rating", "CreateDate", "ModifyDate", "MetadataDate", "title", "description", "creator", "rights", "subject",
            "Make", "Model", "LensModel", "Label", "DocumentID", "OriginalDocumentID"}

def _xmp(path) -> dict:
    raw = open(path, "rb").read(3_000_000)
    i, j = raw.find(b"<x:xmpmeta"), raw.find(b"</x:xmpmeta>")
    if i < 0 or j < 0 or j - i > 200_000: return {}
    pkt = raw[i:j + 12]
    if b"<!DOCTYPE" in pkt or b"<!ENTITY" in pkt: return {}
    out = {}
    root = ET.fromstring(pkt)
    for el in root.iter():
        local = el.tag.split("}")[-1]
        for ak, av in el.attrib.items():
            a = ak.split("}")[-1]
            if a in XMP_KEYS and av.strip(): out.setdefault("XMP " + a, av.strip()[:300])
        if local in XMP_KEYS:
            lis = [li.text.strip() for li in el.iter() if li.tag.endswith("}li") and li.text and li.text.strip()]
            txt = ", ".join(lis) if lis else (el.text or "").strip()
            if txt: out.setdefault("XMP " + local, txt[:300])
    return out

IPTC = {(2, 5): "IPTC Title", (2, 25): "IPTC Keywords", (2, 80): "IPTC Creator", (2, 90): "IPTC City", (2, 101): "IPTC Country",
        (2, 116): "IPTC Copyright", (2, 120): "IPTC Caption"}

def _extras(im, path, out):
    fmt = im.format
    try:
        dpi = im.info.get("dpi")
        if dpi: out["DPI"] = f"{float(dpi[0]):g} x {float(dpi[1]):g}"
    except Exception: pass
    if fmt == "JPEG":
        out["JPEG type"] = "Progressive" if (im.info.get("progressive") or im.info.get("progression")) else "Baseline"
        c = im.info.get("comment")
        if c: out["JPEG comment"] = (c.decode("utf-8", "ignore") if isinstance(c, bytes) else str(c)).strip("\x00 ")[:300]
    try:
        icc = im.info.get("icc_profile")
        if icc:
            from PIL import ImageCms
            out["ICC profile"] = ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(io.BytesIO(icc))).strip() or "Embedded"
    except Exception:
        out["ICC profile"] = "Embedded"
    try:
        n = getattr(im, "n_frames", 1)
        if n > 1: out["Frames"] = n
    except Exception: pass
    if fmt == "PNG":
        for k, v in (getattr(im, "text", None) or {}).items():
            out[f"PNG text: {k}"] = str(v)[:300]
    if fmt in ("JPEG", "TIFF"):
        try:
            from PIL import IptcImagePlugin
            for key, label in IPTC.items():
                v = (IptcImagePlugin.getiptcinfo(im) or {}).get(key)
                if v:
                    vals = v if isinstance(v, list) else [v]
                    out[label] = ", ".join(x.decode("utf-8", "ignore") if isinstance(x, bytes) else str(x) for x in vals)[:300]
        except Exception: pass
    try: out.update(_xmp(path))
    except Exception: pass

def read_exif(path: str) -> tuple[dict, dict]:
    """Returns (all readable fields, camera summary)."""
    out: dict = {}
    with Image.open(path) as im:
        try: ex = im.getexif()
        except Exception: ex = None
        if (ex is None or not len(ex)) and im.format == "JPEG":
            try: ex = _manual_exif(path) or ex
            except Exception: pass
        gps = {}
        if ex is not None:
            ifds = [dict(ex)]
            try: ifds.append(ex.get_ifd(EXIF_IFD))
            except Exception: pass
            try: gps = ex.get_ifd(GPS_IFD)
            except Exception: gps = {}
            for d in ifds:
                for tag, val in d.items():
                    if tag in POINTERS: continue
                    name = ExifTags.TAGS.get(tag)
                    if not name: continue
                    try: f = _fmt(name, val)
                    except Exception: f = None
                    if f not in (None, ""): out[name] = f
        try: _extras(im, path, out)
        except Exception: pass
    if gps:
        out["GPS present"] = "Yes"
        try:
            out["GPS position"] = f"{_dms(gps[2], gps.get(1)):.6f}, {_dms(gps[4], gps.get(3)):.6f}"
        except Exception: pass
        try:
            if 6 in gps and _rat(gps[6]) is not None: out["GPS altitude"] = f"{_rat(gps[6]):.1f} m"
        except Exception: pass
    else:
        out["GPS present"] = "No"
    make, model = out.get("Make"), out.get("Model")
    device = model if (model and make and model.lower().startswith(make.lower())) else " ".join(x for x in (make, model) if x)
    cam = {k: v for k, v in {
        "Device": device, "Make": make, "Model": model, "Lens": out.get("LensModel"), "Software": out.get("Software") or out.get("XMP CreatorTool"),
        "Flash": out.get("Flash"), "Captured": out.get("DateTimeOriginal"), "Focal length": out.get("FocalLength"),
        "Aperture": out.get("FNumber"), "Exposure time": out.get("ExposureTime"), "ISO": out.get("ISOSpeedRatings") or out.get("PhotographicSensitivity"),
    }.items() if v}
    return out, cam
