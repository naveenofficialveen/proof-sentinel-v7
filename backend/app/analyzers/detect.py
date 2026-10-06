import hashlib, magic, os
from .common import UNSUPPORTED

CATEGORIES = {
 "image": {"jpg","jpeg","png","gif","webp","tiff","tif","bmp"},
 "video": {"mp4","mov","avi","mkv","webm","mpeg","mpg"},
 "audio": {"mp3","wav","flac","aac","m4a","ogg"},
 "pdf": {"pdf"},
 "office_xml": {"docx","xlsx","pptx"},
 "office_legacy": {"doc","xls","ppt"},
 "text": {"txt","csv"},
 "archive": {"zip","rar","7z","tar","gz"},
}

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def detect(path: str, filename: str) -> dict:
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    mime = magic.from_file(path, mime=True)
    sig = magic.from_file(path)
    category = next((c for c, exts in CATEGORIES.items() if ext in exts), None)
    # signature/extension sanity: flag mismatches instead of trusting the extension
    mismatch = False
    if category == "image" and not mime.startswith("image/"): mismatch = True
    if category in ("video",) and not (mime.startswith("video/") or mime == "application/octet-stream"): mismatch = True
    if category == "audio" and not mime.startswith("audio/"): mismatch = True
    if category == "pdf" and mime != "application/pdf": mismatch = True
    return {"extension": ext, "mime": mime, "signature": sig,
            "category": category or "unknown",
            "supported": category is not None, "extension_mismatch": mismatch,
            "note": None if category else UNSUPPORTED}
