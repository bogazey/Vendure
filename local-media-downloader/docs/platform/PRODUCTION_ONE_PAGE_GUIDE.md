# Production One-Page Guide (Mission 16, Phase 45)

**This has never been run against real production.** Read
`PRODUCTION_CONTROLLER.md` once before a real cutover. This page is the
day-of quick reference, not the full explanation.

## Normal sequence

```
1.  inspect            # mints a deployment ID, records git/env facts
2.  preflight          # HOST/DISK/RAM/DOCKER/TLS/SECRETS/... category GO/NO-GO
3.  (review the output - resolve any NO-GO before continuing)
4.  backup             # encrypted, checksummed backup with disk-space preflight
5.  verify-backup      # proves the backup actually restores
6.  platform-deploy    # docker compose up - Platform Core only, Loady untouched
7.  platform-verify    # health/ready/JWKS - reports IDENTITY NOT MIGRATED
8.  observe            # (no command - just confirm Loady traffic is unaffected)
9.  migration-dry-run  # zero writes, against a restored SNAPSHOT, not production
10. cutover-check      # aggregates every category - must print OVERALL: GO
11. maintenance-on     # verifies Loady's maintenance mode is actually active
12. migrate            # THE dangerous one - requires --confirm 'MIGRATE <id>'
13. reconcile          # verify-migration.sh - FAIL means ROLLBACK_REQUIRED, not "retry"
14. verify             # safe smoke tests only
15. maintenance-off    # verifies normal traffic resumed
16. monitor            # POST_MIGRATION_MONITORING.md's window-by-window checklist
```

Every command needs `--environment production` (or `rehearsal` for
practice) — there is no default.

## Rollback path (separate from the sequence above)

```
status              # confirm current state and whether rollback_required is true
rollback-plan        # read-only preview - always safe to run
rollback --confirm 'ROLLBACK <id>' [--confirm-restore 'RESTORE-DATABASE <id>']
```

## Checking in mid-sequence, from a fresh terminal

```
scripts/platform/platform-production.sh status --environment production
scripts/platform/platform-production.sh status --environment production --format json
```

## If something looks wrong

```
scripts/platform/platform-production.sh collect-diagnostics --environment production
```
Never includes `.env` contents, tokens, password hashes, private keys, or
customer data — safe to share when asking for help.

## The two confirmation phrases, exactly

- `migrate` needs: `--confirm 'MIGRATE <deployment-id>'`
- `rollback` needs: `--confirm 'ROLLBACK <deployment-id>'`, and if a
  database restore is required, also
  `--confirm-restore 'RESTORE-DATABASE <deployment-id>'`

Get the exact `<deployment-id>` from `status`. Neither accepts `y`,
blank, or anything else.
