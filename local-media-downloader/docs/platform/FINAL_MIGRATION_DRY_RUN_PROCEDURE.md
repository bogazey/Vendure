# Final Migration Dry Run Procedure (Mission 15, Phase 24)

## Exact future command (read directly from `loady_migration_dry_run.py`'s own `argparse` definition — not paraphrased)

```bash
python -m app.scripts.loady_migration_dry_run \
  --loady-database-url sqlite:////path/to/a/restored/read-only/copy/of/commercial.db \
  --reason "Production cutover dry run, <date>"
```

(Omit `--commit` — its mere absence is what makes this a dry run; every
read and write happens exactly as a real run would, inside a transaction
that is rolled back at the very end, per the script's own docstring.)

## Zero-writes guarantee

**Code-verified**, not merely asserted: `run_migration(..., dry_run=not
args.commit)` — the `dry_run` flag threads through to every mutating call
in `loady_migration_service.py`; without `--commit`, the final transaction
is never committed to either database. This is the same mechanism already
exercised by every prior mission's dry-run testing
(`LOADY_MIGRATION_DRY_RUN.md`), re-confirmed here by reading the current
source rather than assumed unchanged.

## Both scripts refuse a URL containing the literal word "production" — confirmed, and a stale docstring corrected

`loady_migration_dry_run.py`'s own module docstring says "this script has
no special handling for 'production'" (line 5) — **this is stale relative
to the code two lines below it**: `if "production" in
args.loady_database_url.lower(): return 1` (line 68-69) is exactly a
production-literal refusal, identical to the guard in
`loady_paddle_reconciliation_dry_run.py`. The actual behavior is *safer*
than the docstring claims, not weaker — a low-severity documentation
staleness, not a functional gap, noted here rather than silently
corrected in that file (per this mission's "don't retroactively rewrite a
prior mission's file" convention) and not a reason to avoid double-naming
the restored snapshot path something that avoids the word "production"
regardless (defense in depth, not reliance on the string check alone).

## Output content — what is and is not safe

The report prints **aggregate counts** (`created=N linked=N skipped=N
conflicted=N failed=N`) followed by **per-row detail for every non-empty
category**, confirmed by reading `loady_migration_dry_run.py`'s print
loop. Each row is a `dict` built in `loady_migration_service.py` —
confirmed by reading every `report.<category>.append({...})` call site:

- **Never present in any row**: password hashes, tokens, secrets.
  `_safe_error_reason()` specifically strips SQLAlchemy `StatementError`
  down to `.orig` (the bare DBAPI message) rather than `str(exc)`,
  because the latter would embed bound parameters — including, for the
  user-creation `INSERT`, the migrated user's Argon2 password hash. This
  is a real, deliberate, already-tested safeguard (its own comment cites
  exactly this risk), not an assumption.
- **Present in CONFLICTED/FAILED rows**: the user's email address and
  Loady user id — necessary for an operator to actually investigate a
  specific conflict/failure, and not a hash/token/secret, but real
  customer PII nonetheless.
- **Present in CREATED/LINKED/SKIPPED rows** (the non-problem categories):
  the same per-user detail, printed unconditionally for every row, not
  just a count. **Operational note, not a security defect**: at real
  production scale (potentially thousands of users), this makes the dry
  run's terminal output far more verbose than "safe aggregate output
  only" suggests — an operator reviewing this output should redirect it
  to a permission-restricted file (`chmod 600`, matching the general
  secret-storage posture) rather than leaving it in shared terminal
  scrollback or a broadly-readable CI log, precisely because it is real
  customer email data even though it contains no credential. This
  mission does not change the script to suppress successful-row detail —
  doing so would be a functional change to already-tested, working
  tooling for a purely cosmetic/verbosity concern, not a "genuine
  production-readiness defect" the No Feature Creep rule's exception
  clause is meant for.

## Review procedure (unchanged from `BILLING_CUTOVER_RUNBOOK.md` Stage 1's established pattern, applied to identity migration)

- `failed` count above zero → investigate each one individually; do not
  proceed until zero or every failure is understood and accepted.
- `conflicted` count above zero on **real** data → stop; this means a
  genuine ambiguity (e.g. an email matching more than one plausible
  record) that must be resolved by a human, never guessed by re-running
  with different flags.
- **Any unexpected conflict is a `NO-GO` for the cutover gate** (Phase 25)
  — this is not a warning-level finding, it blocks the gate outright.

## Relationship to the actual commit step

This dry run must be re-run (not assumed still valid) if any meaningful
time has passed since the snapshot was restored, or if the snapshot is
refreshed — a dry run's report reflects the snapshot's state at restore
time, not live production state. The **commit** run (Stage H of
`LOADY_PRODUCTION_CUTOVER_RUNBOOK.md`) happens during the maintenance
window, against real production, with the identical command plus
`--commit` — and must show the same shape of report as this dry run
(this mission does not change that expectation, already established and
rehearsal-verified by a prior mission).
