#!/bin/sh
# Generates a self-signed TLS certificate for Platform Core staging
# (mission 4, phase 6). Local staging only — never used in production,
# where a real certificate (or an upstream TLS-terminating proxy /
# Cloudflare) replaces it without any other change to nginx.staging.conf.
#
# Usage: ./generate-staging-cert.sh [hostname]
#   hostname defaults to platform-staging.local
set -eu

HOSTNAME="${1:-platform-staging.local}"
OUT_DIR="$(cd "$(dirname "$0")/.." && pwd)/secrets/tls"
mkdir -p "$OUT_DIR"

if [ -f "$OUT_DIR/fullchain.pem" ] && [ -f "$OUT_DIR/privkey.pem" ]; then
    echo "Certificate already exists at $OUT_DIR — remove it first to regenerate."
    exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout "$OUT_DIR/privkey.pem" \
    -out "$OUT_DIR/fullchain.pem" \
    -subj "/CN=$HOSTNAME" \
    -addext "subjectAltName=DNS:$HOSTNAME,DNS:localhost,IP:127.0.0.1"

chmod 600 "$OUT_DIR/privkey.pem"
echo "Self-signed staging certificate written to $OUT_DIR for hostname: $HOSTNAME"
echo "Add '127.0.0.1 $HOSTNAME' to /etc/hosts to browse to it, or add it via curl -k / --resolve."
