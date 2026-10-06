import re, zipfile

def check(path, info):
    """Honest signature status. 'Signature verified' is only returned if real cryptographic verification ran."""
    cat = info["category"]
    if cat == "pdf":
        data = open(path, "rb").read()
        if re.search(rb"/ByteRange|/Type\s*/Sig", data):
            return {"status": "Signature detected", "verified": False,
                    "detail": "PDF signature dictionary found. Cryptographic verification is not performed in this build (verification not supported)."}
        return {"status": "Signature not detected", "verified": False, "detail": None}
    if cat == "office_xml":
        with zipfile.ZipFile(path) as z:
            if any(n.startswith("_xmlsignatures/") for n in z.namelist()):
                return {"status": "Signature detected", "verified": False,
                        "detail": "OOXML digital signature part present; verification not performed."}
        return {"status": "Signature not detected", "verified": False, "detail": None}
    return {"status": "Verification not supported", "verified": False,
            "detail": "No signature verifier is available for this format."}
