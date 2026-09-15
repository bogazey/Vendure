# Production Compose Package Validation (Mission 15, Phase 11)

## What was validated, and how (this environment has no Docker daemon at all — `docker ps`/`docker compose ls` fail with "no such file or directory" on `/var/run/docker.sock`, confirmed again this mission)

`docker compose -f compose.rc.yml --env-file <test-env> config --quiet`
was run against a temporary, non-committed copy of `.env.rc.example` +
`.env.production.example` + `platform-core/.env.production.example` (all
placeholder values, `test-only-value` for the two Postgres passwords —
nothing resembling a real secret). This is **pure client-side YAML
parsing and variable interpolation** — Docker Compose v5.1.1 performs this
without contacting a daemon. **Exit code 0, no errors.** This is
`CODE VERIFIED` for structure (services, networks, volumes, variable
references all resolve), but explicitly **not** `LOCAL LIVE-STACK
VERIFIED` — no image was built, no container started, no healthcheck ran.
That remains `NEEDS EXECUTION`/cutover-day, exactly as
`MISSION_7_ARCHITECTURE_AUDIT.md` §5 already found and left unattempted,
for the same reason restated in Phase 46 below: building and running the
full 7-container stack is meaningfully more resource-intensive than a
config parse, and this mission's environment has no daemon to do it with
regardless of risk tolerance.

## Checklist against Phase 11's explicit requirements

| Requirement | Status |
|---|---|
| No dev servers | Confirmed — both frontends build via multi-stage Dockerfiles into static nginx images (`account-frontend/Dockerfile`, `admin-frontend/Dockerfile`), no `vite dev`/`--host` anywhere in `compose.rc.yml` |
| No source-code bind mounts | Confirmed — every service uses `build:` + named volumes only; the only bind mounts are the TLS directory, the nginx template, and the signing-key file, all read-only (`:ro`) |
| No default credentials | Confirmed — every credential-bearing var (`POSTGRES_PASSWORD`, `PLATFORM_POSTGRES_PASSWORD`) uses `${VAR:?set VAR}`, which makes Compose **fail to start** rather than fall back to a default if unset |
| No committed secrets | Confirmed — `.env.rc`, `.env.production`, `platform-core/.env.production` are all gitignored (only their `.example` counterparts are tracked); the signing key file lives outside the repo entirely (`./platform-core/secrets/`, itself gitignored) |
| Persistent DB volume | Confirmed — `postgres-data`, `platform-postgres-data` both named volumes |
| Persistent signing-key handling | Confirmed — host-path bind mount, not baked into the image or a named volume that Compose could recreate empty |
| Explicit networks | Confirmed — `default` (implicit, Loady-only) + `platform-net` (explicit, `internal: true`) |
| Healthchecks | Confirmed on every service except the two static frontends (`platform-core-account-frontend`/`admin-frontend`), which declare none — acceptable, since `depends_on: condition: service_started` (not `service_healthy`) is used for them by the edge, and their own failure mode is "serves stale/no content," not a crash the edge needs to gate on |
| Restart policies | Confirmed — `unless-stopped` on every service |
| Resource limits | Confirmed — every service has `deploy.resources.limits` (see `PRODUCTION_RESOURCE_BUDGET.md` for the full table and the 7.5 GiB total-memory-limit finding) |
| Log rotation | **Not configured anywhere in `compose.rc.yml`** — no `logging:` driver/options block on any service. **Genuine gap, fixed this mission** (see below) |
| Read-only filesystem where practical | Confirmed on `reverse-proxy`, `platform-core-account-frontend`, `platform-core-admin-frontend` (all static/stateless); **not** set on `backend`/`postgres`/`platform-core-backend`/`platform-core-postgres` — correct, since these write to their own declared volumes and would need extensive `tmpfs` carve-outs for logs/temp files with no real security benefit over the `cap_drop`/`no-new-privileges` hardening already applied |
| `security_opt` where practical | Confirmed — `no-new-privileges:true` on every service |
| No privileged mode | Confirmed — no `privileged: true` anywhere |
| No Docker socket mount | Confirmed — no `/var/run/docker.sock` mount anywhere |
| No unnecessary host ports | Confirmed — only `reverse-proxy` exposes host ports (see `PRODUCTION_ARCHITECTURE_FREEZE.md` port plan) |
| Coexists safely with existing Loady Compose project | Confirmed — `name: loady-rc` is a distinct Compose project name from the existing `loady` project; see the Port Plan's note that this is a **replacement** stack for cutover day, not a concurrently-running addition |
| Explicit project naming | Confirmed — `name: loady-rc` at the top of the file |

## Genuine gap found and fixed: no log rotation

Every container's `stdout`/`stderr` uses Docker's default `json-file`
logging driver with no `max-size`/`max-file` cap. On a single VPS with the
tight disk headroom already flagged in `PRODUCTION_RESOURCE_BUDGET.md`,
unbounded container logs are a real, if slow-moving, path to the exact
disk-exhaustion failure mode `SINGLE_VPS_FAILURE_DOMAIN_REVIEW.md`
identifies as the scariest one on this box (SQLite corruption risk). Fixed
by adding a bounded `logging:` block to every service in `compose.rc.yml`:

```yaml
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

(30 MB cap per container, 7 containers = 210 MB worst case — negligible
against the 5 GiB disk floor, and it prevents an unbounded leak.) This is a
Compose-file change, not application code; it changes no request-handling
behavior, has no test suite of its own to extend (log rotation is an
infrastructure concern verified by `docker compose config` continuing to
parse cleanly, which it does — re-run after the edit, exit 0, no errors),
and directly serves Phase 11's own "log rotation" requirement rather than
being speculative extra scope.

## The one other genuine gap this phase's review surfaced (fixed under Phase 12, not here)

The reverse-proxy template's missing same-origin API routing for the
Account Portal and Grand Admin hostnames — see
`PRODUCTION_REVERSE_PROXY_REVIEW.md` for the full finding and fix; it is a
`nginx.production.conf.template` change, not a `compose.rc.yml` change, so
it is documented there instead of duplicated here.
