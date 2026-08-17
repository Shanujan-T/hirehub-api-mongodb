import hashlib
import os
import secrets
from datetime import timedelta

from app.utils import utc_now

OTP_LENGTH = 6
OTP_TTL_MINUTES = 10


def generate_otp_code() -> str:
    upper = 10**OTP_LENGTH
    return str(secrets.randbelow(upper)).zfill(OTP_LENGTH)


def hash_otp_code(code: str) -> str:
    pepper = os.getenv("OTP_PEPPER", os.getenv("JWT_SECRET_KEY", "dev-secret-key"))
    digest = hashlib.sha256(f"{pepper}:{code.strip()}".encode("utf-8")).hexdigest()
    return digest


def otp_expires_at():
    return utc_now() + timedelta(minutes=OTP_TTL_MINUTES)


def verify_otp_code(code: str, code_hash: str) -> bool:
    if not code or not code_hash:
        return False
    return secrets.compare_digest(hash_otp_code(code), code_hash)
