# Local Rehearsal Results (Mission 15, Phases 46-49)

## Environment constraint, disclosed plainly

**This mission's environment has no Docker daemon at all** —
`/var/run/docker.sock` does not exist; `docker ps`, `docker compose up`,
and any command requiring a running daemon fail immediately with
"Cannot connect to the Docker daemon... is the docker daemon running?".
This is a hard constraint of the sandbox this mission ran in, re-confirmed
this mission (not merely inherited from a prior mission's note). It means
Phases 46/48/49's literal instruction — "run all production operator
scripts against the isolated synthetic environment," "run Platform Core,
Platform PostgreSQL... verify health/routing," "failure-injection... check
GO/NO-GO stops correctly [against running containers]" — **cannot be
executed as literally specified in this environment**. What follows is
exactly what *was* possible without a daemon, stated plainly as such, with
no claim of verification beyond what was actually done.

## Phase 47: protected local stack rule

**Confirmed not applicable in this specific environment, but the rule
itself is preserved and restated as a standing constraint regardless of
environment.** `MISSION_7_ARCHITECTURE_AUDIT.md` §5 records that a prior
mission's environment had a real Docker daemon with what appeared to be a
live personal-use stack bound to host port 80. This mission's environment
has no Docker daemon and therefore no such stack to protect *right now* —
but the rule is not environment-specific, it is a standing safety
constraint: **any future session with a Docker daemon present must check
`docker ps` first and never stop/restart/rebuild/reuse any pre-existing
project's containers, volumes, networks, or ports.** Nothing in this
mission touched, queried, or assumed anything about such a stack, because
none was reachable to touch.

## Phase 46/48: what was actually validated locally, and how

| Artifact | Method | Result |
|---|---|---|
| `compose.rc.yml` | `docker compose config` (pure client-side YAML parse + variable interpolation — Compose v5.1.1 performs this without a daemon) against temporary, non-committed placeholder env files | **Exit 0, clean parse**, both before and after the logging-block addition (`PRODUCTION_COMPOSE_VALIDATION.md`) |
| `nginx.production.conf.template` | Rendered with `envsubst` (restricted to the four `RC_*_HOSTNAME` vars, matching the official nginx image's own entrypoint behavior) + `nginx -t` against a throwaway self-signed cert and temporary `/etc/hosts` entries for the upstream names | **Syntax OK** (with the disclosed nginx-1.24-vs-1.27 `http2 on;` directive caveat — `PRODUCTION_REVERSE_PROXY_REVIEW.md`) |
| `backup-before-platform-migration.sh` (incl. the new disk-space preflight) | Stubbed `docker`/`df` via a fake-bin PATH override, exercising both the NO-GO (insufficient space) and pass-through (sufficient space) branches | `scripts/platform/test-backup-space-preflight.sh` — **both cases pass** |
| `production-preflight-inspection.sh` (new this mission) | Same stubbing technique, exercising GO (all healthy) and NO-GO (bad file permission) | `scripts/platform/test-production-preflight-inspection.sh` — **both cases pass** |
| `cutover-go-no-go.sh` (new this mission) | Same technique, 4 cases: full GO, missing-backup NO-GO, missing-attestation NO-GO, `--json` mode | `scripts/platform/test-cutover-go-no-go.sh` — **all 4 pass** |
| `email_service.py` redaction fix | Real pytest run (not stubbed — this one runs actual application code, not a shell script) | `test_email_service_redaction.py` — **4/4 pass**, plus the pre-existing `test_email_change.py` (5/5) unaffected |
| Every other pre-existing operator script (`preflight-production-migration.sh`, `verify-migration.sh`, `verify-backup-restorable.sh`, `rollback-platform-migration.sh`) | Read in full; **not executed** this mission (no daemon, and no reason to re-rehearse scripts this mission did not modify) | Structurally reviewed only — their own prior-mission rehearsal evidence (`PRODUCTION_REHEARSAL_PLAN.md`) stands, unchanged by this mission |

## Phase 49: failure injection — what was and wasn't possible

**What was actually exercised** (via the stub-based tests above, which
*are* a form of failure injection against these scripts' own logic, just
not against real running containers):

- Insufficient disk space at backup time → correctly refuses (`NO-GO`,
  exit 1) before writing anything.
- Wrong file permission on the signing key → correctly refuses.
- Missing/stale backup at gate time → correctly refuses.
- Unset OAUTH/PADDLE attestation → correctly refuses, never defaults to
  pass.

**What could not be exercised without a Docker daemon** (explicitly
`NEEDS EXECUTION` / cutover-day check, not claimed done):

- Platform Core actually unavailable (a real container stopped mid-request)
  and observing Loady's hybrid fallback behave correctly against a *live*
  Platform Core outage, rather than the already-existing unit-test-level
  proof of the same fallback logic.
- Platform Core DB actually unavailable (a real Postgres container
  stopped) and observing the same.
- A real migration conflict against a populated, running database (only
  proven against synthetic in-process fixtures, not a live container).
- A real backup-checksum failure (corrupting an actual backup file and
  confirming `verify-backup-restorable.sh` catches it) — the script's
  logic was read and is straightforward (`sha256sum -c` semantics), but
  not exercised against a deliberately-corrupted real artifact this
  mission.

## Honest overall disposition for Phases 46-49

**Structurally validated, not proven** — the same distinction
`MISSION_7_ARCHITECTURE_AUDIT.md` applied to `compose.rc.yml` before this
mission is extended here to cover every new/modified artifact from this
mission as well. Every script this mission wrote or modified has real,
passing, stub-based regression tests proving its own internal logic is
correct; none of them have been proven against a real, running,
multi-container Docker environment, because no environment available to
this mission has ever had a working Docker daemon. This is the single
most consequential gap in this mission's evidence, stated plainly rather
than hidden behind confident-sounding language, and is carried into the
final GO/NO-GO document (Phase 55) as exactly that: a real, named
limitation, not a checked box.
