"""RS256 signing key management for OIDC-style tokens.

Uses the standard `cryptography` library to generate/load an RSA keypair —
no custom cryptography (mission-brief section 38). The private key never
leaves this service; only the public key is published, in standard JWK
format, at `GET /.well-known/jwks.json` so resource servers (products) can
verify token signatures without ever holding a shared secret.

Dev/local behavior: if no key file exists yet at
`settings.jwt_private_key_path` AND `app_env == "development"`, one is
generated and written there on first use — analogous to Loady's
`SECRET_KEY` falling back to a randomly generated value rather than a
fixed "dev" constant.

Staging/production behavior (mission 4, phase 3): the private key MUST be
provisioned out of band — a mounted secret file at `JWT_PRIVATE_KEY_PATH`
— before the process starts. If it is missing in any non-development
`APP_ENV`, key loading fails closed with `SigningKeyUnavailableError`
rather than silently generating a throwaway key that would invalidate
every previously issued token on the next restart. This is enforced again,
explicitly, at startup (`app.main`'s readiness check) so the failure
surfaces immediately rather than lazily on the first login.
"""
from __future__ import annotations

import base64
import functools
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config.settings import get_settings


class SigningKeyUnavailableError(RuntimeError):
    """Raised when no RS256 private key is available and this environment
    is not allowed to generate one on the fly."""


def _b64url_uint(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    raw = value.to_bytes(length, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@functools.lru_cache(maxsize=1)
def _load_or_create_private_key() -> rsa.RSAPrivateKey:
    settings = get_settings()
    path = Path(settings.jwt_private_key_path)
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)

    if settings.app_env != "development":
        raise SigningKeyUnavailableError(
            f"No RS256 signing key found at JWT_PRIVATE_KEY_PATH={path!s} and "
            f"APP_ENV={settings.app_env!r} does not allow generating one at "
            "startup. Provision the key out of band (mounted secret) before "
            "starting Platform Core in staging/production."
        )

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.parent.mkdir(parents=True, exist_ok=True)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_bytes(pem)
    path.chmod(0o600)
    return key


def signing_key_is_available() -> bool:
    """Non-raising check for readiness probes: is a signing key already on
    disk, or would this environment be allowed to generate one? Never loads
    or returns key material."""
    settings = get_settings()
    if Path(settings.jwt_private_key_path).exists():
        return True
    return settings.app_env == "development"


def validate_signing_key_material() -> None:
    """Fail-closed startup check (mission 4, phase 3): raises
    `SigningKeyUnavailableError` immediately if this process cannot obtain
    a signing key, instead of waiting for the first token request."""
    _load_or_create_private_key()


def get_private_key_pem() -> bytes:
    key = _load_or_create_private_key()
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def get_public_key_pem() -> bytes:
    key = _load_or_create_private_key().public_key()
    return key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def get_jwks() -> dict:
    """The public JWK Set — safe to expose to anyone, always. Never
    includes any private material."""
    settings = get_settings()
    public_numbers = _load_or_create_private_key().public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": settings.jwt_key_id,
                "n": _b64url_uint(public_numbers.n),
                "e": _b64url_uint(public_numbers.e),
            }
        ]
    }
