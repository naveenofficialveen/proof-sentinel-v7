NA = "Not Available"
UNSUPPORTED = "Unsupported / Analysis Not Available"

def clean(d: dict) -> dict:
    """Replace empty values with 'Not Available'; never invent data."""
    return {k: (v if v not in (None, "", [], {}) else NA) for k, v in d.items()}
