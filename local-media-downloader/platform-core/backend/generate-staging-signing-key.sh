#!/bin/sh
# Provisions the RS256 signing key out of band (mission 4, phase 3) so the
# backend container never generates one itself in staging/production -
# see app/security/jwt_keys.py's fail-closed behavior for APP_ENV != development.
#
# Usage: ./generate-staging-signing-key.sh [output-path]
#   output-path defaults to ../secrets/platform-signing-key.pem
set -eu

OUT_PATH="${1:-$(cd "$(dirname "$0")/.." && pwd)/secrets/platform-signing-key.pem}"
mkdir -p "$(dirname "$OUT_PATH")"

if [ -f "$OUT_PATH" ]; then
    echo "Signing key already exists at $OUT_PATH — remove it first to rotate/regenerate."
    exit 0
fi

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$OUT_PATH"
chmod 600 "$OUT_PATH"
echo "RS256 signing key written to $OUT_PATH"
echo "Set JWT_PRIVATE_KEY_PATH to this path (mounted read-only into the backend container)."
