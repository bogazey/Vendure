#!/usr/bin/env bash
set -euo pipefail

base_url="${BASE_URL:-https://loady.cc}"
failures=0

check_status() {
  local path="$1" expected="$2" actual
  actual="$(curl --silent --show-error --location --output /dev/null --write-out '%{http_code}' "${base_url}${path}")"
  if [[ "$actual" != "$expected" ]]; then
    printf 'FAIL %s: expected %s, got %s\n' "$path" "$expected" "$actual" >&2
    failures=$((failures + 1))
  else
    printf 'PASS %s (%s)\n' "$path" "$actual"
  fi
}

for path in / /en /ar /en/video-downloader /ar/video-downloader /en/audio-downloader /ar/audio-downloader /en/image-downloader /ar/image-downloader /robots.txt /sitemap.xml /api/health; do
  check_status "$path" 200
done
for path in /this-route-must-not-exist /.env /.git/config /api/docs /openapi.json; do
  check_status "$path" 404
done

if (( failures > 0 )); then
  printf '%d smoke check(s) failed.\n' "$failures" >&2
  exit 1
fi
printf 'All deterministic public smoke checks passed.\n'
