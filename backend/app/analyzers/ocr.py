import cv2, pytesseract

def _ocr_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
    words = [(w, int(c)) for w, c in zip(data["text"], data["conf"]) if w.strip() and int(c) > 0]
    text = " ".join(w for w, _ in words)
    conf = round(sum(c for _, c in words) / len(words), 1) if words else None
    return text, conf

def ocr_image_file(path):
    img = cv2.imread(path)
    if img is None: return {"status": "failed", "text": None, "confidence": None}
    text, conf = _ocr_image(img)
    return {"status": "completed" if text else "no_text_detected", "text": text or None, "confidence": conf}

def ocr_video_frames(path, samples=5):
    cap = cv2.VideoCapture(path); total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    results = []
    for i in range(samples if total else 0):
        idx = int(total * (i + 0.5) / samples); cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok: continue
        text, conf = _ocr_image(frame)
        results.append({"frame": idx, "text": text or None, "confidence": conf})
    cap.release()
    found = [r for r in results if r["text"]]
    return {"status": "completed" if found else "no_text_detected", "frames": results}
