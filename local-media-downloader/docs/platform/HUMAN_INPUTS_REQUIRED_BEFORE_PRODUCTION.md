# Human Inputs Required Before Production (Mission 15, Phase 53)

Only things genuinely requiring the owner/operator's own decision or
possession — nothing this mission could have produced itself. **Never
paste a secret value into a chat with an AI assistant** — every "provide"
instruction below means directly into the target environment/file, never
into this conversation.

| Input | Why required | When required | Safe to provide how |
|---|---|---|---|
| Identity hostname decision (`id.loady.cc` vs. long-term alternative) | Business/branding decision — `IDENTITY_DOMAIN_DECISION.md` recommends the default but does not decide it | Before Phase 13 (Cloudflare DNS records) can be created | A one-line confirmation to whoever manages DNS; no secret involved |
| Production Postgres passwords (Loady's own, if rotating; Platform Core's new one) | Real credentials, must be generated and stored directly in `.env.rc`/`.env.production` on the VPS | Before first `docker compose ... up` of the combined stack | Generate on the VPS itself (`openssl rand -base64 32`, per `PRODUCTION_SECRET_BOOTSTRAP.md`), write directly into the env file with `chmod 600`, never transmit elsewhere |
| RS256 signing key + `JWT_KEY_ID` | Real cryptographic material | Before Platform Core first starts | Generate on the VPS (`openssl genrsa`), `chmod 600`, per `PRODUCTION_SECRET_BOOTSTRAP.md` |
| `COOKIE_SIGNING_KEY`, `PLATFORM_TOKEN_ENCRYPTION_KEY`, `WEBHOOK_SECRET_ENCRYPTION_KEY` | Real cryptographic material | Same | Same |
| `PLATFORM_CLIENT_ID`/`SECRET` (Loady's registration) | Issued by running `register_loady_client.py` against the real Platform Core database | Stage 4 of `LOADY_PRODUCTION_MIGRATION_PLAN.md`, after migration commit | Run the script on the server itself; capture its one-time printed output directly into Loady's env file |
| TLS certificate covering `id./account./admin.loady.cc` | Requires knowing which CA/tool the existing `loady.cc` cert uses (unknown to this mission — `TLS_CERTIFICATE_PLAN.md`) | Before Phase 14's cutover proceeds | Whatever the existing renewal process already uses (certbot/Cloudflare Origin CA) — an operator decision, not a value to transmit anywhere |
| Cloudflare DNS record creation authorization | This mission is explicitly forbidden from touching Cloudflare | Before Phase 13's plan can be executed | The owner or whoever holds Cloudflare access performs it directly per `CLOUDFLARE_CUTOVER_PLAN.md` |
| Production inspection authorization | This mission is explicitly forbidden from any production access, even read-only | Before `production-preflight-inspection.sh` is ever run against the real VPS | An explicit go-ahead from the owner; the script itself requires no secret to run, only SSH/exec access the owner controls |
| Maintenance-window approval | Business decision — affects real users | Before `FINAL_PRODUCTION_CUTOVER_RUNBOOK.md` is scheduled | A scheduling confirmation, no secret involved |
| Cutover authorization (the actual go/no-go to execute) | This mission explicitly does not authorize production deployment | Before any step of `FINAL_PRODUCTION_CUTOVER_RUNBOOK.md` runs for real | An explicit, separate decision from the owner, made with this mission's full package in hand |
| Paddle Live webhook secret + dashboard access (only if billing cutover is also pursued) | Real Paddle credential | `BILLING_CUTOVER_RUNBOOK.md` Stage 2c | Set directly in Platform Core's env file by whoever has Paddle dashboard access; never transmitted elsewhere |
| Off-site backup destination (real remote storage account/credentials) | Currently unconfigured anywhere (`PRODUCTION_BACKUP_PACKAGE.md`) | Before relying on off-site backup for disaster recovery | Configure `BACKUP_OFFSITE_CMD` directly on the VPS with real destination credentials |
| Confirmation of Loady's real `alembic_version` value | Needed to rule out the two orphaned revision IDs found this mission (`DATABASE_MIGRATION_SAFETY_REVIEW.md`) | Before running `alembic upgrade head` against real production | A single read-only `SELECT` the operator runs themselves |
| Confirmation `oauth_clients.webhook_signing_secret` is empty in production | Needed before Platform Core's `8e2a4ae9d31e` migration ever runs against a populated database (`DATABASE_MIGRATION_SAFETY_REVIEW.md`) | Same | Same — a single read-only `SELECT` |

## What this mission explicitly does NOT need from the owner right now

- No secret value of any kind — every credential above is generated or
  issued *by the operator, on the target system*, never handed to this
  mission.
- No decision that only affects a later, separate effort (billing cutover
  specifics beyond the webhook secret, long-term domain consolidation) —
  those are flagged in their own documents as deferred, not blocking this
  package.
