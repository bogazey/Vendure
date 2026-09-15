# Cutover GO/NO-GO Gate (Mission 15, Phase 25)

Implemented as `scripts/platform/cutover-go-no-go.sh`, tested by
`scripts/platform/test-cutover-go-no-go.sh` (4 cases, all passing — GO
when every category is satisfied, NO-GO when a backup is missing/stale,
NO-GO when the OAUTH attestation is unset, and a `--json` machine-readable
mode). **Never executed against anything real** — every test run used a
stubbed `docker`/`df`/`free` and a throwaway temp directory.

## The eleven categories, exactly as Phase 25 requires, and how each is decided

| Category | How it's decided | Automatable? |
|---|---|---|
| HOST | Delegates to `production-preflight-inspection.sh` (Docker/Compose versions, disk/RAM/swap/load) | Fully automated |
| DATABASE | Same script's DB-connectivity + record-count checks | Fully automated |
| LOADY | Same script's container-health check for Loady's containers | Fully automated |
| PLATFORM | Same script's container-health check for Platform Core's containers | Fully automated |
| SECRETS | Same script's signing-key/TLS file presence + permission checks. **Does not** verify secret *values* are correct (impossible without decrypting/using them) — only that the expected files exist with the expected mode | Partially automated |
| RESOURCE CAPACITY | Same evidence as HOST (disk/RAM/swap/load) — a distinct category per Phase 25's list, not a distinct check | Fully automated |
| BACKUPS | A backup directory for the target env must exist, be less than 24 hours old, and have a `CHECKSUMS.sha256` manifest present | Fully automated |
| ROLLBACK READINESS | `rollback-platform-migration.sh` must exist and be executable, and a valid (per BACKUPS) backup must exist to restore from | Fully automated |
| MIGRATION | Requires `MIGRATION_DRY_RUN_REPORT_PATH` pointing at a saved dry-run report (Phase 24 procedure) showing `failed=0 conflicted=0` | Automated **given** the operator ran and saved the dry run first — this gate does not run the dry run itself |
| OAUTH | Requires an explicit `OAUTH_REDIRECT_URI_VERIFIED=yes` operator attestation | **Cannot be automated** without a live call against the real registered OAuth client — see below |
| PADDLE | `N/A` unless `BILLING_CUTOVER_IN_SCOPE=yes` (this identity cutover does not include billing cutover by default, per Decision #6); if in scope, requires `PADDLE_SANDBOX_PARITY_VERIFIED=yes` | **Cannot be automated** for the same reason as OAUTH |

## Why OAUTH and PADDLE require an explicit attestation rather than a live check

This mission has no network access to production, Paddle, or any OAuth
endpoint to verify against (Absolute Safety Boundary). A gate that
silently marked these categories "GO" without any real check — or worse,
made a live call to verify them — would either lie about what was
verified or violate the boundary. An explicit, unset-by-default
environment variable is the honest alternative: it forces a human to have
actually performed the check described in
`PRODUCTION_DEPLOYMENT_SEQUENCING.md` step 7 (OAUTH) or
`BILLING_CUTOVER_RUNBOOK.md` Stage 2b (PADDLE) and to say so explicitly,
rather than the gate assuming silence means yes. **An unset attestation is
always NO-GO** — there is no code path that defaults it to GO.

## Machine-readable output

`--json` emits:

```json
{
  "overall": "GO",
  "categories": {
    "HOST": {"status": "GO", "reason": ""},
    "...": "..."
  }
}
```

Exit code mirrors the overall verdict (`0` for GO, `1` for NO-GO) either
way, so this gate is usable directly as a CI/pipeline step's condition
without parsing output at all, while still supporting a human reading the
plain-text form.

## No ambiguous state for a mandatory condition

Every category resolves to exactly `GO`, `NO-GO`, or (PADDLE only, when
out of scope) `N/A` — never left unset or partially evaluated. The overall
verdict is `NO-GO` if **any** category (excluding `N/A`) is `NO-GO` — a
single failing category blocks the whole cutover, matching Phase 25's
explicit requirement.
