"""PKCE (RFC 7636) verification — the standard `S256` transform only.
`plain` is deliberately never accepted (mission-brief section 24:
"missing PKCE" is a named threat; accepting the no-op `plain` method would
effectively be that).
"""
from __future__ import annotations

import base64
import hashlib


def compute_s256_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_pkce(code_verifier: str, code_challenge: str, code_challenge_method: str) -> bool:
    if code_challenge_method != "S256":
        return False
    if not (43 <= len(code_verifier) <= 128):
        return False
    return compute_s256_challenge(code_verifier) == code_challenge
