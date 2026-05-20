"""CWE-327: Use of Broken or Risky Cryptographic Algorithm.

Deva will flag MD5 for password hashing and DES for encryption.
"""

import hashlib
import secrets


def hash_password_vulnerable(pw: str) -> str:
    # BAD: MD5 has been considered broken for password storage since 2004.
    # Anyone who exfiltrates the database can crack short passwords in seconds.
    return hashlib.md5(pw.encode()).hexdigest()


def hash_password_safe(pw: str, salt: bytes | None = None) -> tuple[str, bytes]:
    """The fix: a slow, salted, memory-hard hash designed for passwords."""
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return digest.hex(), salt


def hash_for_integrity(data: bytes) -> str:
    # BAD: SHA-1 is broken for collision resistance.
    return hashlib.sha1(data).hexdigest()


def hash_for_integrity_safe(data: bytes) -> str:
    """The fix: SHA-256 or stronger."""
    return hashlib.sha256(data).hexdigest()
