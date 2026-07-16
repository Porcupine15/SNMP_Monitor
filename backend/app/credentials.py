"""Encryption boundary for SNMP credentials stored in the database."""

import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)
PREFIX = "enc:"


def _fernet() -> Optional[Fernet]:
    key = os.getenv("CREDENTIALS_ENCRYPTION_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError("CREDENTIALS_ENCRYPTION_KEY must be a Fernet key") from exc


def encrypt(value: Optional[str]) -> Optional[str]:
    if not value or value.startswith(PREFIX):
        return value
    cipher = _fernet()
    if cipher is None:
        logger.warning("SNMP credentials are not encrypted: CREDENTIALS_ENCRYPTION_KEY is unset")
        return value
    return PREFIX + cipher.encrypt(value.encode()).decode()


def decrypt(value: Optional[str]) -> Optional[str]:
    if not value or not value.startswith(PREFIX):
        return value
    cipher = _fernet()
    if cipher is None:
        raise RuntimeError("Encrypted credential found but CREDENTIALS_ENCRYPTION_KEY is unset")
    try:
        return cipher.decrypt(value.removeprefix(PREFIX).encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt an SNMP credential") from exc


def protect_device_credentials(data: dict) -> dict:
    protected = data.copy()
    for field in ("community", "snmp_user", "snmp_auth", "snmp_priv"):
        if field in protected:
            protected[field] = encrypt(protected[field])
    return protected


def device_credentials(device) -> dict:
    return {
        "community": decrypt(device.community),
        "snmp_user": decrypt(device.snmp_user),
        "snmp_auth": decrypt(device.snmp_auth),
        "snmp_priv": decrypt(device.snmp_priv),
    }
