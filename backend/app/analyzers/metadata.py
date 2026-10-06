import codecs, csv, datetime as dt, hashlib, json, os, subprocess, tarfile, zipfile
from xml.etree import ElementTree as ET
from .common import NA, UNSUPPORTED, clean

def _ts(t): return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()

def with_optional(core: dict, optional: dict) -> dict:
    """Core fields always appear ('Not Available' when empty). Optional fields appear only when the file really has them."""
    out = clean(core)
    out.update({k: v for k, v in optional.items() if v not in (None, "", [], {})})
    return out

def general(path, filename, info):
    st = os.stat(path)
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        head = f.read(64)
        md5.update(head)
        for chunk in iter(lambda: f.read(1 << 20), b""):
            md5.update(chunk)
    return clean({"File name": filename, "File type": info["mime"], "Extension": info["extension"],
                  "File size (bytes)": st.st_size, "File signature": info["signature"],
                  "MD5 (legacy checksum)": md5.hexdigest(),
                  "Header, first 64 bytes (hex)": " ".join(f"{b:02X}" for b in head),
                  "Filesystem modified (server copy)": _ts(st.st_mtime)})

def image_meta(path):
    from PIL import Image
    from .exifutil import read_exif
    out = {}
    with Image.open(path) as im:
        out.update({"Format": im.format, "Dimensions": f"{im.width}x{im.height}", "Mode": im.mode,
                    "Megapixels": round(im.width * im.height / 1e6, 2)})
    exif, cam = read_exif(path)
    out.update(exif)
    if not cam and not any(k in exif for k in ("Make", "Model", "Software", "DateTimeOriginal")):
        out["EXIF camera data"] = "Not present in this file"
    return clean(out), cam

def ffprobe_meta(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-show_chapters", path],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0: return {"error": "ffprobe could not parse this file"}, [], {}
    j = json.loads(r.stdout); fmt = j.get("format", {}); streams = j.get("streams", [])
    v = next((s for s in streams if s["codec_type"] == "video"), {})
    a = next((s for s in streams if s["codec_type"] == "audio"), {})
    tags = {k.lower(): val for k, val in fmt.get("tags", {}).items()}
    def tag(*names):
        for n in names:
            if tags.get(n): return tags[n]
    fps = None
    if v.get("avg_frame_rate") and v["avg_frame_rate"] != "0/0":
        n, d = v["avg_frame_rate"].split("/"); fps = round(int(n) / int(d), 3) if int(d) else None
    rot = (v.get("tags") or {}).get("rotate") or next((sd.get("rotation") for sd in v.get("side_data_list", []) if "rotation" in sd), None)
    make = tag("com.apple.quicktime.make", "com.android.manufacturer", "make", "manufacturer")
    model = tag("com.apple.quicktime.model", "com.android.model", "model")
    software = tag("encoder", "software", "com.apple.quicktime.software")
    created = tags.get("creation_time")
    location = tag("location", "com.apple.quicktime.location.iso6709")
    meta = with_optional(
        {"Container": fmt.get("format_long_name"), "Duration (s)": fmt.get("duration"), "Bit rate": fmt.get("bit_rate"),
         "Number of streams": fmt.get("nb_streams"), "Resolution": f'{v.get("width")}x{v.get("height")}' if v else None,
         "Frame rate": fps, "Video codec": v.get("codec_name"), "Audio codec": a.get("codec_name"),
         "Creation time": created, "Encoder/Software": software, "Device make": make, "Device model": model},
        {"Brand": tags.get("major_brand"), "Chapters": len(j.get("chapters", [])) or None, "Video profile": v.get("profile"),
         "Pixel format": v.get("pix_fmt"), "Color space": v.get("color_space"), "Rotation": rot,
         "Sample rate": a.get("sample_rate"), "Channels": a.get("channels"), "Channel layout": a.get("channel_layout"),
         "Android version": tags.get("com.android.version"), "Location": location, "Title": tags.get("title"), "Artist": tags.get("artist"),
         "Album": tags.get("album"), "Genre": tags.get("genre"), "Date": tags.get("date"), "Track": tags.get("track"),
         "Comment": tags.get("comment"), "Copyright": tags.get("copyright")})
    structure = [{"index": s.get("index"), "type": s.get("codec_type"), "codec": s.get("codec_name")} for s in streams]
    cam = {k: val for k, val in {"Device": " ".join(x for x in (make, model) if x), "Make": make, "Model": model,
                                  "Software": software, "Captured": created, "Location": location}.items() if val}
    return meta, structure, cam

def pdf_meta(path):
    from pypdf import PdfReader
    r = PdfReader(path); m = r.metadata or {}
    opt = {"Subject": m.get("/Subject"), "Keywords": m.get("/Keywords")}
    try: opt["PDF version"] = str(r.pdf_header).replace("%PDF-", "")
    except Exception: pass
    try:
        box = r.pages[0].mediabox; w, h = float(box.width), float(box.height)
        opt["Page size"] = f"{w:.0f} x {h:.0f} pt ({w / 72 * 25.4:.0f} x {h / 72 * 25.4:.0f} mm)"
    except Exception: pass
    try:
        root = r.trailer["/Root"]
        if "/MarkInfo" in root: opt["Tagged PDF"] = "Yes"
        if "/Metadata" in root: opt["XMP metadata"] = "Present"
    except Exception: pass
    try:
        f = r.get_fields()
        if f: opt["Form fields"] = len(f)
    except Exception: pass
    raw = open(path, "rb").read(20_000_000)
    if b"/JavaScript" in raw or b"/JS" in raw: opt["JavaScript"] = "Detected"
    if b"/EmbeddedFile" in raw: opt["Embedded files"] = "Detected"
    return with_optional({"Pages": len(r.pages), "Title": m.get("/Title"), "Author": m.get("/Author"), "Producer": m.get("/Producer"),
                          "Creator": m.get("/Creator"), "Created": m.get("/CreationDate"), "Modified": m.get("/ModDate"),
                          "Encrypted": "Yes" if r.is_encrypted else "No"}, opt)

def _small(z, name, limit=5_000_000):
    return z.read(name) if name in z.namelist() and z.getinfo(name).file_size <= limit else None

def office_xml_meta(path):
    core, opt = {}, {}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        ns = {"dc": "http://purl.org/dc/elements/1.1/", "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
              "dcterms": "http://purl.org/dc/terms/"}
        raw = _small(z, "docProps/core.xml")
        if raw:
            root = ET.fromstring(raw)
            g = lambda p: (root.find(p, ns).text if root.find(p, ns) is not None else None)
            core.update({"Author": g("dc:creator"), "Last modified by": g("cp:lastModifiedBy"), "Title": g("dc:title"),
                         "Created": g("dcterms:created"), "Modified": g("dcterms:modified")})
            opt.update({"Subject": g("dc:subject"), "Keywords": g("cp:keywords"), "Comments": g("dc:description"),
                        "Category": g("cp:category"), "Revision": g("cp:revision"), "Last printed": g("cp:lastPrinted")})
        raw = _small(z, "docProps/app.xml")
        if raw:
            root = ET.fromstring(raw)
            for el in root:
                tag = el.tag.split("}")[1]
                if tag in ("Application", "AppVersion", "Company"): core[tag] = el.text
                elif tag in ("Manager", "Template", "TotalTime", "Pages", "Words", "Characters", "Lines", "Paragraphs", "Slides", "Notes", "HiddenSlides", "DocSecurity"):
                    opt[tag] = el.text
        raw = _small(z, "docProps/custom.xml")
        if raw: opt["Custom properties"] = len(list(ET.fromstring(raw))) or None
        if any(n.endswith("comments.xml") for n in names): opt["Comments in document"] = "Present"
        if any(n.endswith("vbaProject.bin") for n in names): opt["Macros"] = "Present"
        n_emb = sum(1 for n in names if "/embeddings/" in n)
        if n_emb: opt["Embedded objects"] = n_emb
        doc = _small(z, "word/document.xml", 30_000_000)
        if doc and (b"<w:ins " in doc or b"<w:del " in doc): opt["Tracked changes"] = "Present"
    return with_optional(core, opt)

def office_legacy_meta(path):
    import olefile
    if not olefile.isOleFile(path): return {"note": UNSUPPORTED}
    o = olefile.OleFileIO(path); m = o.get_metadata()
    dec = lambda b: b.decode("latin-1") if isinstance(b, bytes) else b
    return clean({"Author": dec(m.author), "Last saved by": dec(m.last_saved_by), "Title": dec(m.title),
                  "Application": dec(m.creating_application), "Created": str(m.create_time) if m.create_time else None,
                  "Modified": str(m.last_saved_time) if m.last_saved_time else None})

def text_meta(path):
    with open(path, "rb") as f: raw = f.read(1 << 20)
    if raw.startswith(codecs.BOM_UTF8): enc = "UTF-8 with BOM"
    elif raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)): enc = "UTF-16"
    else:
        try: raw.decode("utf-8"); enc = "UTF-8 (or plain ASCII)"
        except UnicodeDecodeError: enc = "Not UTF-8 (other encoding or binary)"
    crlf = raw.count(b"\r\n"); lf = raw.count(b"\n") - crlf; cr = raw.count(b"\r") - crlf
    kinds = [n for n, c in (("Windows (CRLF)", crlf), ("Unix (LF)", lf), ("Old Mac (CR)", cr)) if c]
    endings = "None" if not kinds else kinds[0] if len(kinds) == 1 else "Mixed"
    opt = {}
    try:
        sample = raw[:4096].decode("utf-8", "ignore")
        d = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        opt["Probable delimiter"] = {"\t": "tab"}.get(d.delimiter, d.delimiter)
        opt["Columns in first row"] = len(next(csv.reader(sample.splitlines(), d)))
    except Exception: pass
    return with_optional({"Encoding (first 1 MB)": enc, "Line endings": endings, "Line count (first 1 MB)": raw.count(b"\n")}, opt)

def archive_meta(path, ext):
    out, structure = {}, []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            infos = z.infolist(); out["Entries"] = len(infos)
            out["Encrypted entries"] = sum(1 for i in infos if i.flag_bits & 1)
            out["Uncompressed size (bytes)"] = sum(i.file_size for i in infos)
            out["Compressed size (bytes)"] = sum(i.compress_size for i in infos)
            if z.comment: out["Archive comment"] = z.comment.decode("utf-8", "ignore")[:300]
            structure = [{"name": i.filename, "size": i.file_size} for i in infos[:200]]
    elif tarfile.is_tarfile(path):
        with tarfile.open(path) as t:
            ms = t.getmembers(); out["Entries"] = len(ms); out["Uncompressed size (bytes)"] = sum(m.size for m in ms)
            structure = [{"name": m.name, "size": m.size} for m in ms[:200]]
    elif ext == "7z":
        import py7zr
        with py7zr.SevenZipFile(path) as z:
            out["Entries"] = len(z.getnames()); structure = [{"name": n} for n in z.getnames()[:200]]
    elif ext == "rar":
        import rarfile
        with rarfile.RarFile(path) as z:
            out["Entries"] = len(z.infolist()); structure = [{"name": i.filename, "size": i.file_size} for i in z.infolist()[:200]]
    else:
        return {"note": UNSUPPORTED}, []
    return clean(out), structure

def extract(path, filename, info):
    cat, structure, cam = info["category"], [], {}
    try:
        if cat == "image": m, cam = image_meta(path)
        elif cat in ("video", "audio"): m, structure, cam = ffprobe_meta(path)
        elif cat == "pdf": m = pdf_meta(path)
        elif cat == "office_xml":
            m = office_xml_meta(path)
            with zipfile.ZipFile(path) as z: structure = [{"part": n} for n in z.namelist()]
        elif cat == "office_legacy": m = office_legacy_meta(path)
        elif cat == "text": m = text_meta(path)
        elif cat == "archive": m, structure = archive_meta(path, info["extension"])
        else: m = {"note": UNSUPPORTED}
    except Exception:
        m = {"Note": "Some metadata could not be read (the file may be damaged, protected or an unusual variant)"}
    return {"general": general(path, filename, info), "specific": m, "structure": structure, "camera": cam}
