"""RFC 7636 PKCE helper - identical algorithm to what
`platform-core/backend/app/security/pkce.py` verifies server-side and
what `demo-product-a/backend/app.py::_pkce_pair` hand-rolled."""
from __future__ import annotations

import base64
import hashlib
import secrets


def generate_pkce_pair() -> tuple[str, str]:
    """Returns (code_verifier, code_challenge). The verifier is kept by
    the product (in a short-lived httpOnly cookie, never exposed to
    JavaScript); the challenge is sent to Platform Core's
    `/oauth/authorize`."""
    verifier = secrets.token_urlsafe(64)[:64]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge
