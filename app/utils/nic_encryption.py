import os
import re

from cryptography.fernet import Fernet, InvalidToken

NIC_PATTERN = re.compile(r"^(\d{9}[VvXx]|\d{12})$")


def validate_nic_format(nic_number: str) -> bool:
    return bool(NIC_PATTERN.match(str(nic_number).strip()))


def _get_fernet() -> Fernet:
    key = os.getenv("NIC_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("NIC encryption is not configured.")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_nic(nic_number: str) -> str:
    normalized = str(nic_number).strip().upper()
    return _get_fernet().encrypt(normalized.encode()).decode()


def decrypt_nic(encrypted_value: str) -> str:
    try:
        return _get_fernet().decrypt(encrypted_value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted NIC value.") from exc


def mask_nic(nic_number: str) -> str:
    value = str(nic_number).strip()
    if len(value) <= 4:
        return "••••"
    return "•" * (len(value) - 4) + value[-4:]
