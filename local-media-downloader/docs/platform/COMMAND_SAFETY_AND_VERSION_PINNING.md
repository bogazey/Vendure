# Command Safety and Version Pinning (Mission 15, Phases 27-28)

## Phase 27: command safety

Every operator script this mission wrote or reviewed follows the same
convention, confirmed by direct reading, not assumed:

| Requirement | Status |
|---|---|
| `set -euo pipefail` | Present in every script: `backup-before-platform-migration.sh`, `verify-backup-restorable.sh`, `preflight-production-migration.sh`, `verify-migration.sh`, `rollback-platform-migration.sh`, and this mission's new `production-preflight-inspection.sh`, `cutover-go-no-go.sh` |
| Hostname/working-dir validation | Not applicable at the shell-script level today (these scripts operate on named Docker containers, not hostnames/paths implying "this machine is production") — the actual safety mechanism is the `--env production` flag combined with `:?`-mandatory env vars (below), which is a stronger, more explicit guard than a hostname string match would be |
| Git commit/branch validation | `preflight-production-migration.sh` already checks `EXPECTED_BRANCH` against the current branch and refuses on a mismatch or a dirty tree — confirmed present in the version read this mission |
| Compose project / environment marker validation | `--env staging\|production` is mandatory on every script that takes it; production mode additionally requires every container/credential name as an explicit `:?`-mandatory var — **no script silently guesses a production value**, confirmed across every script this mission touched |
| DB target validation | Every DB-touching script takes the target container/database/user as an explicit named argument, never a positional guess (see `PLATFORM_POSTGRES_PRODUCTION_PLAN.md`'s "preventing accidental backup/restore against the wrong DB" section) |
| Required-file validation | `production-preflight-inspection.sh` (this mission) checks signing-key and TLS file presence/permissions before declaring GO |
| Dangerous commands require explicit confirmation, never blank-as-yes | `backup-before-platform-migration.sh` and `rollback-platform-migration.sh` both require `PLATFORM_MIGRATION_CONFIRM=I_UNDERSTAND_THIS_IS_PRODUCTION` set to an exact literal string for production mode — an unset or blank value is treated as "no," never as "yes." The new `cutover-go-no-go.sh` gate applies the identical pattern for its two non-automatable attestations (`OAUTH_REDIRECT_URI_VERIFIED=yes`, `PADDLE_SANDBOX_PARITY_VERIFIED=yes`) — an unset or any-other-value is always `NO-GO`, never defaulted to pass. |
| Never print secrets | Confirmed across every script: `backup-before-platform-migration.sh`'s configuration inventory captures variable **names** only (`cut -d= -f1`); `production-preflight-inspection.sh` checks the signing key's file **mode**, never its contents; the disk-space preflight added this mission reads database **sizes**, never contents |

**No script this mission reviewed or wrote fails this checklist.** No new
guard was needed beyond what already existed, except the disk-space
preflight (Phase 20, a new check, not a new command-safety *pattern* —
it follows the identical `NO-GO: <reason>; exit 1` convention every other
check in these scripts already uses).

## Phase 28: deployment version pinning

- **Never deploy "latest"**: `compose.rc.yml` builds every custom image
  from its own Dockerfile (`build: context: ...`) rather than pulling a
  floating tag; the two base images it does pull are version-pinned
  (`postgres:16-alpine`, `nginx:1.27-alpine` via
  `platform-core/reverse-proxy/Dockerfile`) — confirmed by direct read,
  no `:latest` tag anywhere in the compose file or either Dockerfile.
- **Record on every deploy** (procedure, not yet automated — a genuine gap
  worth naming rather than silently assuming covered):
  - Git commit hash (`git rev-parse HEAD`) of the branch actually deployed.
  - Docker image build identity — since these are locally built, not
    pulled, the meaningful identity is the git commit above plus the
    Dockerfile's own content hash; no separate image registry/tag exists
    for this single-VPS deployment model, which is an accepted V1 choice
    (matches Loady's own existing deployment pattern — confirmed, Loady's
    `compose.production.yml` also builds locally rather than pulling a
    tagged image).
  - Alembic migration revision (`alembic current`) for both services —
    already captured by `backup-before-platform-migration.sh`'s
    `migration_versions.txt`.
  - Deployment timestamp — captured naturally by the backup run's own
    timestamped directory name and by shell history/deployment logs the
    operator keeps (out of scope for this mission to mandate a specific
    logging tool).
- **Rollback must identify the previous version**: `FINAL_PRODUCTION_ROLLBACK_RUNBOOK.md`'s
  full-restore path restores to the exact database state captured in the
  FINAL BACKUP step, which itself records the pre-rollback (i.e.
  about-to-be-superseded) Alembic revision in `migration_versions.txt` —
  the previous version is whatever that file says, not a guess.
- **Genuine gap, documented not fixed**: there is no automated "current
  deployed commit" marker file/label on the running containers themselves
  (e.g. a `DEPLOYED_COMMIT` env var baked in at build time) — an operator
  relying on shell history alone to know what's currently running is a
  real, if minor, operational risk. Not fixed here: adding a build-time
  commit-stamping mechanism is a reasonable future hardening step, but
  building it now, untested against a real deploy pipeline that doesn't
  exist yet, would be speculative rather than addressing a demonstrated
  failure.
