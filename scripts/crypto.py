"""
Field-level encryption for Neo4j node properties.

Each user gets a unique Fernet key derived from ENCRYPTION_SECRET + their user_id via HKDF.
Nodes use a stable HMAC hash (_h) as the MERGE identity key so deduplication still works
without storing plaintext.
"""
import os
import hmac as _hmac
import hashlib
import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


def _secret() -> bytes:
    s = os.getenv("ENCRYPTION_SECRET", "")
    if not s:
        raise RuntimeError("ENCRYPTION_SECRET env var is not set")
    return s.encode()


def _user_fernet(user_id: str) -> Fernet:
    kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=user_id.encode(),
    )
    key = base64.urlsafe_b64encode(kdf.derive(_secret()))
    return Fernet(key)


def enc(value: str, user_id: str) -> str:
    """Encrypt a string value for a user."""
    if not value:
        return value or ""
    return _user_fernet(user_id).encrypt(value.encode()).decode()


def dec(value: str, user_id: str) -> str:
    """
    Decrypt a string value for a user.
    Returns the value as-is if decryption fails (handles unencrypted legacy data).
    """
    if not value:
        return value or ""
    try:
        return _user_fernet(user_id).decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return value


def node_hash(value: str, user_id: str) -> str:
    """
    Stable HMAC-SHA256 of (user_id, value) used as the _h property in MERGE queries.
    Allows Neo4j to deduplicate nodes without storing plaintext.
    """
    msg = f"{user_id}:{value.lower().strip()}".encode()
    return _hmac.new(_secret(), msg, hashlib.sha256).hexdigest()


def dec_props(props: dict, user_id: str) -> dict:
    """Decrypt all known string fields in a property dict."""
    if not props:
        return props or {}
    result = dict(props)
    for field in ("name", "key", "value", "description", "speaking_style"):
        if field in result and isinstance(result[field], str):
            result[field] = dec(result[field], user_id)
    return result
