# Local Development

Everything below was actually run, end-to-end, during this mission
(Platform Core + Grand Admin + two demo products, all on `localhost`,
across five separate processes) - this is not an untested description.

## Prerequisites

- Python 3.11, Node 22 (matching Loady's own toolchain).
- No production domain, no real payment processor, no real email service
  required (mission-brief section 30).

## 1. Platform Core backend

```bash
cd local-media-downloader/platform-core/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="sqlite:///$(pwd)/data/platform_dev.db"
export PLATFORM_AUTH_BASE_URL="http://localhost:8100"   # must match how
                                                          # you'll browse to it -
                                                          # see SSO.md's cookie-
                                                          # domain note below
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

`data/platform_dev.db` and `data/jwt_signing_key.pem` are created on first
run and gitignored - never commit them (see the repo's
`.gitignore` for the `platform-core/**` entries added by this mission).

### Bootstrap an admin and the demo clients

```bash
# in a second terminal, same venv activated, same DATABASE_URL exported
curl -X POST http://localhost:8100/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"a-strong-password-1"}'

python -m app.scripts.promote_super_admin admin@example.com
python -m app.scripts.register_demo_clients   # prints DEMO_CLIENT_SECRET
                                               # for demo-a and demo-b - paste
                                               # into each demo app's .env
```

`register_demo_clients` and `promote_super_admin` are both idempotent and
CLI-only - there is no HTTP path to either (same posture as Loady's own
`promote_admin` script). `python -m app.scripts.seed_products` seeds the
full ten-product registry (`loady`, `gamey`, `filey`, ...) if you want
Grand Admin's Products page populated beyond the two demo products.

## 2. Grand Admin frontend

```bash
cd local-media-downloader/platform-core/admin-frontend
npm install
npm run dev   # http://localhost:5273
```

Sign in with the admin account promoted above. `VITE_PLATFORM_API_BASE_URL`
defaults to `http://localhost:8100`; override it if Platform Core runs
elsewhere.

## 3. Demo Product A / B

```bash
cd local-media-downloader/platform-core/demo-product-a/backend
python3 -m venv .venv && source .venv/bin/activate    # or reuse demo-a's venv - identical requirements.txt
pip install -r requirements.txt
cp .env.example .env   # fill in DEMO_CLIENT_SECRET from register_demo_clients above
set -a; source .env; set +a
python -m uvicorn app:app --host 127.0.0.1 --port 9301
```

Repeat for `demo-product-b` on port `9302`. Open
`http://localhost:9301` in a browser, click "Sign in with Central
Identity", create an account (or sign in if you already have one), and
you'll land back on demo-a's dashboard showing your `usr_...` global id.
Opening `http://localhost:9302` in the **same** browser reaches demo-b
with no further login - that's the SSO acceptance test, live (see `SSO.md`
§"Live proof" for exactly what was run and observed, screenshots included
in the mission's final report).

### The localhost cookie-domain note

Platform Core's session cookies have no explicit `Domain=` attribute, so
they default to the exact host used in the request. **Use `localhost`
consistently** (not a mix of `localhost` and `127.0.0.1`) across
`PLATFORM_AUTH_BASE_URL`, the browser URL bar, and any script driving the
flow - browsers and cookie jars treat `localhost` and `127.0.0.1` as
different hosts even though they resolve to the same machine, and a
mismatch silently breaks SSO with no error message (encountered and fixed
during this mission's own live testing).

## 4. Running the automated test suites

```bash
# Platform Core backend
cd local-media-downloader/platform-core/backend && source .venv/bin/activate
pytest -q

# Grand Admin frontend
cd local-media-downloader/platform-core/admin-frontend
npm run typecheck && npm run lint && npm test && npm run build
```

## Database boundaries (mission-brief section 26/27)

Platform Core's database (`platform.db` in dev) contains **only**:
`users`, `refresh_tokens`, `email_verification_tokens`,
`password_reset_tokens`, `products`, `product_memberships`,
`oauth_clients`, `authorization_codes`, `oauth_refresh_tokens`, `plans`,
`entitlements`, `payment_records`, `roles`, `role_assignments`,
`audit_logs`. It has no table for Loady's download history, no table for
any future product's operational data, and never will - a product only
ever talks to Platform Core through the OIDC exchange and
`/api/v1/entitlements/me`, never a direct DB connection. A failure in one
product's own database can never touch this one, and vice versa
(mission-brief section 27).

## What this mission deliberately did NOT touch

- `local-media-downloader/backend` and `local-media-downloader/frontend`
  (Loady itself) - zero files modified.
- `.env.production`, any Paddle/Resend/Cloudflare/TLS credential.
- Any production database.
- Nothing was deployed anywhere.
