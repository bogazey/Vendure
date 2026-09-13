# Platform Core Backup / Restore (Mission 4, Phase 17)

Staging-only procedure, rehearsed for real against the actual staging
PostgreSQL container. Production adds encryption-at-rest and off-site
storage requirements (below) not yet implemented anywhere.

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
