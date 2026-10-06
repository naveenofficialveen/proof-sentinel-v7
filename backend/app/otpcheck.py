"""One-time-code checking, kept free of database/web code so it can be tested on its own."""
import hashlib, hmac
from datetime import datetime, timezone

MAX_ATTEMPTS = 5

def otp_hash(otp: str, user_id: int, secret: str) -> str:
    return hashlib.sha256(f"{otp}:{user_id}:{secret}".encode()).hexdigest()

def evaluate(record, otp: str, user_id: int, secret: str, now: datetime | None = None) -> bool:
    """True only for a correct, unused, unexpired code with attempts left. A wrong code counts as an attempt."""
    now = now or datetime.now(timezone.utc)
    if record is None or record.used_at is not None or record.expires_at < now or record.attempts >= MAX_ATTEMPTS:
        return False
    if not hmac.compare_digest(record.otp_hash, otp_hash(otp, user_id, secret)):
        record.attempts += 1
        return False
    return True
