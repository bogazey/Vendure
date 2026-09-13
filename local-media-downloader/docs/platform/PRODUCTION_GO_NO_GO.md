# Production Migration Go/No-Go Preflight (Mission 5, Phase 26)

`scripts/platform/preflight-production-migration.sh` is the single source
of truth for whether a migration commit run should proceed. It prints
**exactly one** of:

```
GO
```
or
```
NO-GO:
  - <reason 1>
  - <reason 2>
  ...
```

There is no third, ambiguous outcome — the script's exit code is `0` for
`GO` and `1` for `NO-GO`, so it composes directly into any automation
(`preflight-production-migration.sh --env production && commit-migration.sh`).

## What it checks

1. Git: expected branch (`unified-platform-v1` in staging mode; operator-
   supplied in production mode) and a clean working tree.
2. Docker daemon reachable.
3. At least 5 GiB free disk space.
4. Loady and Platform Core backend containers report `healthy`.
5. Loady's `/api/health` and Platform Core's `/ready` both return success.
6. Platform Core's readiness response reports `signing_key: true`.
7. `PLATFORM_TOKEN_ENCRYPTION_KEY` is set on the Loady backend container
   (name only — the check never reads or prints the value).
8. Loady reports its Platform Core OAuth client is configured
   (`/api/auth/platform/status` → `{"enabled": true}`).
9. Both services report their Alembic migrations at `head` — no
   unexpected pending/failed migrations on either side.
10. The backup destination directory exists and is writable.

## What it deliberately does NOT check

- Real production DNS/Cloudflare/TLS state — this mission never had
  access to verify that live, and the script doesn't pretend to.
- Whether a human has actually read the cutover runbook. That's an
  organizational control, not a technical precondition.
- Database connectivity beyond the readiness endpoints already
  transitively proving it (a separate raw `pg_isready` check was judged
  redundant — if `/ready` says the database is up, it is).

## Staging vs. production

Staging mode (`--env staging`) is fully self-contained — it hardcodes the
known staging container names and URLs, exactly as they exist on this
machine, and was run repeatedly during Mission 5 (including a deliberate
NO-GO reproduction: stopping `platform-core-staging-backend-1` produced
four accurate, specific reasons; restarting it and waiting for the
health check to settle returned to a clean `GO`).

Production mode (`--env production`) requires every container
name/URL/branch to be supplied via environment variables — nothing about
the real production topology is hardcoded into this script. **This
mission never ran production mode** — it is written and structured for a
future operator, per the Absolute Safety Rule, and has not itself been
executed against anything but staging.

## Using it in the cutover

See `LOADY_PRODUCTION_CUTOVER_RUNBOOK.md`, section G — the preflight
script's `GO` output is the explicit, required gate before the migration
commit step is allowed to run. A `NO-GO` result stops the cutover at that
point; the maintenance window is lifted and nothing further happens
until every listed reason is resolved and the check is run again.
