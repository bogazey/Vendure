# Container Security Review (Mission 15, Phase 45)

Every Dockerfile in the combined stack read in full this mission
(`platform-core/backend/Dockerfile`, `backend/Dockerfile`,
`platform-core/account-frontend/Dockerfile`,
`platform-core/admin-frontend/Dockerfile`, plus `compose.rc.yml`'s own
security fields for every service).

| Check | Finding |
|---|---|
| Running user | Both backends run as a dedicated non-root user (`platform` uid 10101, `loady` uid 10001); both frontend runtime stages use the stock `nginx:1.27-alpine` image's own `nginx` user (unchanged from upstream) |
| Privileged mode | Not set anywhere in `compose.rc.yml` |
| Capabilities | `cap_drop: [ALL]` on every service; `cap_add` limited to the minimum each actually needs (`reverse-proxy`/frontends: `CHOWN, DAC_OVERRIDE, SETGID, SETUID, NET_BIND_SERVICE` for nginx's own privilege-drop-then-bind pattern; `postgres`: adds `FOWNER` on top for its own file-ownership needs; `backend`/`platform-core-backend`: no `cap_add` at all beyond the drop) |
| Docker socket | Not mounted anywhere |
| Host mounts | Only the TLS directory and the signing-key file are bind-mounted, both read-only (`:ro`); no source-code bind mount anywhere in the production compose file |
| Secret leakage via build | **Genuine gap found and fixed this mission**: `platform-core/account-frontend/` had no `.dockerignore`, unlike its sibling `platform-core/admin-frontend/` (which excludes `node_modules`/`dist`/`.env`/`.env.staging`/`.git`). Since the account-frontend's `Dockerfile` does `COPY . .` in its build stage, any local `.env`/`.env.staging` file present in that directory on the build machine would have been copied into the intermediate build-stage layer (not the final shipped image, since only `/app/dist` is copied forward — but still a real, avoidable exposure via layer caching/`docker history`). **Fixed**: added `platform-core/account-frontend/.dockerignore`, byte-identical to the admin-frontend's. |
| Build context / `.dockerignore` (everything else) | `platform-core/backend/`, `backend/`, `frontend/` all have their own `.dockerignore` — confirmed present. `platform-core/reverse-proxy/` has none, but its `Dockerfile` only `COPY`s one named file (`nginx.staging.conf`), never the whole context, so a missing `.dockerignore` there is a build-context-size inefficiency, not a secret-exposure path — not fixed, lower priority than the account-frontend case which does `COPY . .` |
| Image size | Not measurable without a Docker daemon to actually build (`NEEDS EXECUTION`, cutover-day/next-session check) — `python:3.12-slim` and `node:22-alpine`/`nginx:1.27-alpine` base images are all already the slim/alpine variants, which is the size-conscious choice available without further action |
| Package / dev tooling in the final image | Platform Core backend: single-stage build, installs only `ca-certificates`, `libpq5`, `tini` via apt (no compiler toolchain, `apt` cache removed same layer); Loady backend: same pattern (confirmed by reading `backend/Dockerfile`). Both frontends are genuinely multi-stage — the Node build toolchain never reaches the final `nginx:1.27-alpine` runtime stage, only the built `dist/` output does |
| Public ports | Only `reverse-proxy` exposes any (`PRODUCTION_ARCHITECTURE_FREEZE.md` port plan) |
| Healthchecks | Present on every service except the two static frontends, which use `service_started` dependency instead — a deliberate, reasonable choice already assessed in `PRODUCTION_COMPOSE_VALIDATION.md` |

## Genuine gaps found this phase: 1 (fixed)

The `.dockerignore` fix is the only container-security-specific finding —
everything else already matches good practice, consistent with the
non-root/tini/capability-dropping pattern established across every
service in this codebase.

## What this review does not sacrifice functionality for

- `--forwarded-allow-ips=*` on both backends' uvicorn invocation trusts
  `X-Forwarded-*` headers from any caller — acceptable specifically
  because neither backend has a host port; the only things that can reach
  them at all are the edge (on `platform-net`) or Loady's own
  server-to-server call, both already-trusted callers within this
  single-VPS network topology. This is not weakened or "fixed" here
  because doing so (e.g. hardcoding a specific trusted-proxy IP) would add
  fragility for no real security gain given the actual network isolation
  already in place.
- No `read_only: true` filesystem was added to the two application
  backends (`backend`, `platform-core-backend`) — both write to their own
  declared volumes and log to stdout; forcing a read-only root filesystem
  on them would require extensive `tmpfs` carve-outs for temp files with
  no corresponding security benefit beyond what `cap_drop`/
  `no-new-privileges` already provide, so this was assessed and
  deliberately not changed, not overlooked.
