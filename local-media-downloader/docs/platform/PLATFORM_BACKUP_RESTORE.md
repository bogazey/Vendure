# Platform Core Backup / Restore (Mission 4, Phase 17)

Staging-only procedure, rehearsed for real against the actual staging
PostgreSQL container. Encryption-at-rest, file permissions, and
retention are now implemented and verified (see "Mission 7 additions"
below) — real off-site storage to separate infrastructure is the one
requirement from the original list still not configured anywhere.

## Backup

```sh
# From the host, using the running staging postgres container:
source .env.staging
docker exec platform-core-staging-postgres-1 \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c -f /tmp/staging_backup.dump
docker cp platform-core-staging-postgres-1:/tmp/staging_backup.dump ./staging_backup.dump
```

`-F c` (custom format) is used rather than plain SQL: it compresses, and
`pg_restore` can selectively restore or reorder objects from it if ever
needed. Credentials are read from `.env.staging` (gitignored), never
hard-coded into a script.

## Restore rehearsal (actually performed)

Restored into a **separate**, freshly created PostgreSQL container — not
back into the same staging instance — to prove the dump is actually
self-contained and usable elsewhere, not just "the file exists":

```sh
docker run -d --name restore-test --user 70:70 \
  -e POSTGRES_DB=platform_core_restore_test \
  -e POSTGRES_USER=platform_staging \
  -e POSTGRES_PASSWORD=restore-test-password \
  postgres:16-alpine

docker cp staging_backup.dump restore-test:/tmp/staging_backup.dump
docker exec restore-test pg_restore -U platform_staging -d platform_core_restore_test \
  --no-owner --role=platform_staging /tmp/staging_backup.dump
```

**Real finding from the rehearsal**: the first restore attempt, without
`--no-owner --role=<target_user>`, printed 16 `ALTER TABLE ... OWNER TO
platform_core_staging` errors, because the target database's role
(`platform_staging`) didn't match the original database's owning role
(`platform_core_staging`) — an entirely realistic scenario when restoring
into a different environment with different credentials. The data itself
restored fine either way (`pg_restore` continues past ownership errors by
default and warns), but `--no-owner --role=<target_user>` is the correct,
clean way to do it and produces zero errors. Documented here, not
silently worked around, since a runbook that hides a warning a real
operator would see during an actual incident is worse than useless.

Verified after restore, directly via SQL, into the separate database:

- `SELECT id, email, status FROM users;` — the super-admin account
  created during the rehearsal was present.
- `SELECT role_slug, scope FROM role_assignments;` — `super_admin` /
  `global` was present.
- `SELECT version_num FROM alembic_version;` — present and matched the
  source database's current head, meaning the restored database is
  immediately usable by a freshly started application without needing to
  re-run migrations.

Membership, entitlement, audit-log, and OAuth-client rows are the same
mechanism (plain tables in the same dump) — not re-verified row-by-row in
this rehearsal beyond the tables above, since the restore mechanism
itself (not any one table) was what needed proving.

## Production requirements not yet implemented

- **Encryption at rest / in transit for the backup file itself.** This
  rehearsal's dump sat unencrypted on local disk and inside a plain
  `docker cp`. Production needs the dump encrypted (e.g. `age` or GPG)
  before it leaves the database host.
- **Off-site storage.** A backup that lives only on the same host as the
  database it backs up does not survive that host's failure. Production
  needs an automated push to separate storage (object storage in a
  different region/provider, at minimum).
- **Automation and retention policy.** This rehearsal was a manual,
  one-time `pg_dump`. Production needs a scheduled job with a defined
  retention window and a periodic *automated* restore-and-verify drill
  (not just a one-time manual one, as done here) to catch backup rot
  before it's needed for real.
- **Access control on backup files.** Whoever can read a backup can read
  every user's data (password hashes, though Argon2id; OAuth client
  secrets, hashed; audit history in full). Production access to the
  backup storage location must be as restricted as production database
  access itself.

## Mission 5 additions: checksums, restore-testing, secret separation, permissions

The requirements above (encryption, off-site storage, automation) remain
unimplemented — this section adds what Mission 5 actually built and
verified, and states the remaining requirements explicitly per the
mission brief.

- ✅ **Checksums** — `scripts/platform/backup-before-platform-migration.sh`
  writes a `CHECKSUMS.sha256` alongside every backup artifact.
  `scripts/platform/verify-backup-restorable.sh` checks it **before**
  attempting any restore, and this was proven to actually catch
  corruption: a deliberately-corrupted **copy** of a real backup (40
  bytes overwritten mid-file) was correctly rejected
  (`loady_postgres.dump: FAILED`, exit 1, `NO-GO`) without ever
  attempting to restore it, while the original, untouched backup
  verified and restored cleanly immediately after (Mission 5, phase 24).
- ✅ **Restore testing** — not a one-time manual check: both Postgres
  dumps (Loady's and Platform Core's) and the Loady SQLite history file
  were independently restored/integrity-checked in throwaway,
  network-isolated Docker resources multiple times across this mission
  (phases 5 and 24), and a **live production-style rollback** actually
  restored a real backup into the running staging database and verified
  the application worked correctly against it end-to-end (phase 21) —
  the strongest form of "restore testing" available short of production
  itself.
- **File permissions** — not yet enforced by tooling as of Mission 5.
  The backup directory and every file in it should be `chmod 600`/`700`
  (owner-only) at minimum; this mission's scripts do not currently set
  permissions explicitly (they inherit the umask of whoever runs them) —
  a MEDIUM-severity gap to close before production, tracked in
  `PRODUCTION_READINESS_CHECKLIST.md`. **Closed in Mission 7** — see
  below.
- **Secret separation** — confirmed by design and re-verified this
  mission: `backup-before-platform-migration.sh`'s configuration
  inventory captures environment variable **names only**
  (`cut -d= -f1`), never values — spot-checked live in phase 5 (the
  inventory correctly lists `PADDLE_API_KEY` as a name with no value
  anywhere in the file). Database dumps themselves necessarily contain
  password **hashes** (Argon2id) and OAuth client secret **hashes**, never
  plaintext credentials — this is the existing, unchanged security
  property of both databases' own schemas, not something backup tooling
  adds or could remove.
- **Retention** — as of Mission 5, still entirely unautomated.
  Recommendation for an initial production policy, absent any
  automation: keep the last 7 daily backups plus the last backup taken
  immediately before any migration/cutover event, until off-site
  automated backups exist. **Automated pruning added in Mission 7** —
  see below (the "keep 7 daily + pre-cutover" policy recommendation
  above still applies as the retention *window* to configure via
  `--retention-days`; this mission added the mechanism, not a mandated
  number).
- **Off-server recommendation** — as of Mission 5, unchanged, still a
  BLOCKER for production. For the local rehearsal specifically, every
  backup produced by this mission is gitignored
  (`docs/platform/rehearsal-artifacts/`) and never leaves this machine —
  correct for a rehearsal, but a reminder that "committed to git" is
  never an acceptable substitute for real off-site backup storage even
  if it were not explicitly forbidden here. **Mission 7 built the
  off-site push mechanism** (see below) but a real destination is still
  not configured — this remains the one genuinely open item.

## Mission 7 additions: encryption, file permissions, retention, off-site hook

Closes most of "Production requirements not yet implemented" above —
run and verified for real against the live staging containers
(`loady-staging-postgres-1`, `platform-core-staging-postgres-1`,
`loady-staging-backend-1`), not just read/reasoned about:

- ✅ **Encryption at rest** — every data artifact
  (`loady_postgres.dump`, `loady_app.db`, `platform_core_postgres.dump`)
  is now encrypted with `openssl enc -aes-256-cbc -pbkdf2` immediately
  after being written, and the plaintext is deleted in the same step -
  `BACKUP_ENCRYPTION_PASSPHRASE` is a hard requirement
  (`backup-before-platform-migration.sh` refuses to run without it, in
  both staging and production mode - there is no plaintext-fallback
  mode). `age`/GPG were this doc's original suggestions; neither is
  installed on this machine, so `openssl` (already present everywhere)
  was used instead - equivalent encryption-at-rest property, swap in
  `age`/GPG later if preferred, nothing else about the pipeline depends
  on which tool does the encryption. Verified end-to-end this mission:
  ran a real backup against the staging containers, confirmed only
  `.enc`/`.txt`/`.sha256` files exist on disk (no plaintext dump ever
  left behind), then ran `verify-backup-restorable.sh` against it -
  decrypt → checksum-verify → restore into an isolated container all
  succeeded, and a **wrong passphrase** was confirmed to fail loudly
  (`openssl` "bad decrypt", `pg_restore` "does not appear to be a valid
  archive", non-zero exit) rather than silently producing corrupt data.
- ✅ **File permissions** — `chmod 700` on the run directory, `chmod 600`
  on every file in it, immediately after checksums are computed.
  Verified: `ls -la` on a real run directory showed `drwx------` /
  `-rw-------` throughout. Closes the MEDIUM-severity gap Mission 5 left
  open.
- ✅ **Retention** — `--retention-days N` prunes backup run-directories
  older than N days under `--out` on every invocation (`find ... -mtime
  +N`). Verified: created a fake backup directory dated 2020-01-01,
  confirmed it was removed by a real invocation with
  `--retention-days 30` while newer directories were kept.
- **Off-site storage — mechanism built and verified, real destination
  still NOT configured.** `--offsite` invokes `$BACKUP_OFFSITE_CMD` (an
  operator-supplied shell command template, the run directory passed as
  `$1`) after the backup completes - no specific provider is hard-coded,
  matching this doc's original "object storage in a different region/
  provider, at minimum" framing without prescribing which one. Verified
  the invocation mechanism actually fires and receives the correct
  directory using a local stand-in (`cp -r "$1" ...`) as
  `BACKUP_OFFSITE_CMD` - genuinely proves the hook works, but this
  environment has no real cloud storage account/rclone remote/etc. to
  push to, so an actual off-site transfer to separate infrastructure
  remains **UNTESTED** and is **still the one open item from this
  section** before "backup encryption/off-site" can be called fully
  resolved. Whoever configures a real `BACKUP_OFFSITE_CMD` (e.g. `rclone
  copy "$1" remote:bucket/platform-backups/`) should re-verify the push
  actually lands before trusting it.
- **Automation (scheduling)** — still not built. `--retention-days` and
  `--offsite` make the script itself capable of running unattended, but
  nothing here adds a cron job/systemd timer/CI schedule to actually
  invoke it periodically - that wiring is environment-specific
  (production may run on the host directly; the local rehearsal in
  `compose.rc.yml` doesn't need a schedule at all) and deliberately left
  to the deployment target, not this repo's tooling.

## Mission 6 addendum (Phase 47)

Every new V2 table (`entitlement_definitions`, `plan_entitlements`,
`subscriptions`, `subscription_items`, `billing_webhook_events`,
`gifted_access`, `bundles`, `bundle_product_plans`, `bundle_access`,
`service_grants`, `outbox_events`) and every new column on `payment_records`/
`oauth_clients`/`users` requires **no change** to the backup/restore
mechanism above: `pg_dump -F c` captures the entire database schema and
every table in it, whatever that schema currently is - there is no
per-table allowlist anywhere in `backup-before-platform-migration.sh` to
update. This was verified by reading the script, not by re-running the
actual rehearsal: **this mission did not re-execute the live
backup/restore rehearsal against a real Postgres instance** (no
staging/production database access - mission-brief Phase 56) and does
not claim to have. Report Phase 47 as **architecturally covered,
operationally UNTESTED** against the actual V2 schema until someone
re-runs `PRODUCTION_ROLLBACK_REHEARSAL.md`'s procedure for real.
