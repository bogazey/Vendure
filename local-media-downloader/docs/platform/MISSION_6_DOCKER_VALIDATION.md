# Mission 6 Continuation — Docker / Full-Stack Validation

Executed, not skipped (the prior Mission 6 session did not run Docker
builds at all). Isolation was mandatory and verified both before and
after.

## Isolation

- Before starting: enumerated every running container (`docker ps`) -
  the pre-existing personal-use stack (`loady-*`, `loady-staging-*`,
  `platform-core-staging-*`, `open-webui`, `searxng`, `open-terminal`)
  was left completely alone throughout.
- The validation stack used its own Compose project name
  (`mission6-validation`), its own Docker network
  (`mission6-validation_default`, auto-created and auto-removed), and
  host ports that don't collide with anything already published
  (`18100`, `18101` vs. the existing stack's `80`, `8090`, `8091`,
  `8443`).
- After validation: `docker compose down -v` removed every container,
  the network, and the anonymous Postgres volume; the built images were
  explicitly `docker rmi`'d. Confirmed afterward via `docker ps` that
  every pre-existing container was still running with the same uptime it
  had before this session touched Docker at all (e.g.
  `platform-core-staging-postgres-1: Up 3 hours (healthy)`, unchanged).

## What was built and run

1. **`platform-core/backend/Dockerfile`** - builds cleanly on the exact
   current source (all Mission 6 continuation code included:
   `routes_catalog.py`, `routes_account.py`, `catalog_service.py`,
   `revenue_service.py`, `secret_encryption.py`, etc.).
2. **`platform-core/admin-frontend/Dockerfile`** - builds cleanly
   (`npm ci && npm run build`, then an nginx runtime stage).
3. **A one-off isolated Compose stack** (Postgres 16 + backend +
   admin-frontend) brought up with `docker compose up -d --build`. The
   backend's own `docker-entrypoint.sh` ran `alembic upgrade head`
   against the fresh containerized Postgres automatically on startup -
   this is a *third*, independent confirmation the migration chain
   applies cleanly (after the SQLite and the manually-driven Postgres
   validation in `MISSION_6_POSTGRESQL_VALIDATION.md`), this time via the
   exact startup path a real deployment uses.
4. **HTTP smoke tests against the running containers** (not just
   container health checks):
   - `GET /health` → `{"status": "ok"}`
   - `GET /ready` → `{"status": "ok", "checks": {"database": true,
     "signing_key": true}}` - proves the containerized app actually
     talked to the containerized Postgres and found/loaded a signing key.
   - `GET /.well-known/jwks.json` → a real RSA public key.
   - `POST /api/v1/auth/signup` → a real user created in the
     containerized Postgres, with a real session cookie returned.
   - `GET /api/v1/products` (authenticated via that cookie) → `[]`
     (correct - empty product registry on a fresh database).
   - `GET /api/v1/admin/system-health` (anonymous) → `401` (correct -
     the new Mission 6 continuation endpoint is properly protected in the
     containerized deployment too).
   - admin-frontend's nginx served `200` on `/`.

## What was NOT done

- **The Account Portal was not containerized or run** - it does not
  exist yet (see the final report - it remains the largest not-built
  item this session).
- **The reverse-proxy/TLS layer** (`compose.staging.yml`'s
  `reverse-proxy` service) was not part of this validation - out of
  scope for "does the application build and run in containers," which
  is what was asked.
- **No demo product container** was brought up in this pass - the SDK's
  own live-server integration test (`test_live_server_onboarding.py`,
  from the prior session) already exercises the SSO+entitlement flow
  against a real running Platform Core process, just not inside Docker
  specifically.
- **Not pushed to any registry** - images were built locally, smoke
  tested, and deleted.
