# Recovery Time Targets (Mission 15, Phase 40)

All numbers below are either directly measured (staging rehearsal) or
explicitly marked as an estimate/unknown — never fabricated.

| Activity | Estimate/measurement | Basis |
|---|---|---|
| Maintenance window (identity migration only) | 10-15 minutes | `MAINTENANCE_WINDOW_PLAN.md`, based on real staging timings (migration commit + reconciliation well under a minute at 51 synthetic users) |
| Layer 1 rollback (kill switch) | **5 seconds, measured** | `PRODUCTION_ROLLBACK_REHEARSAL.md` Phase 22 |
| Layer 2 rollback, mechanical steps only (DB restore + container switch + validation), backup already on local disk | **110 seconds (~1 min 50s), measured** | Same source — 51s DB restore + 14s container switch + 40s validation, at 54-user staging scale |
| Layer 2 rollback, real production estimate | **10-20 minutes, planning estimate** | Dominated by backup **retrieval** time (off-server storage not yet configured — a documented gap, not measured) and human decision time, not the mechanical restore, which scales with database size (production is larger than the 54-user staging measurement) |
| Central-disable propagation SLA | **~5 minutes documented, 302 seconds measured live** | `SESSION_REVOCATION.md`, `PRODUCTION_REHEARSAL_PLAN.md` phase 18 |
| Cross-product SSO revocation bound | **~15 minutes (OIDC access-token TTL default)** | `MISSION_7_ARCHITECTURE_AUDIT.md` §1 — bounded by the cached token's own TTL, not instant |
| Backup creation time (production scale) | **Unknown — `PRODUCTION PREFLIGHT REQUIRED`** | Only measured at small synthetic-staging scale; the new disk-space preflight (Phase 20) prevents an undersized destination from causing a failed/truncated backup, but does not predict how long a large real backup takes |
| Full stack restart (Docker daemon/host reboot recovery) | **Unknown — `PRODUCTION PREFLIGHT REQUIRED`** | No real-host reboot has been measured; only container-level restarts within an already-running Docker daemon have been rehearsed (Mission 5 phase 19, full-stack restart proven byte-identical, timing not the focus of that rehearsal) |

## What this means for planning the cutover window

The maintenance window's own 10-15 minute estimate is independent of the
rollback-time estimates above — rollback (if ever needed) happens **after**
declaring the window's steps have failed, and is its own separate time
budget on top of the window itself. An operator should plan for the
possibility that a cutover attempt consumes: the base window (10-15 min)
+ validation steps (a few minutes each) + potentially a full rollback
(10-20 min) if something goes wrong late — i.e. budget up to roughly
45-60 minutes of total possible elapsed time for the worst reasonable case
that still ends in a known-good state (either forward on the new
architecture or fully rolled back), not just the happy-path 10-15 minutes.

## What remains genuinely unknown until production preflight

- Real production user-table size (drives migration-commit and backup/restore
  duration).
- Real production disk I/O characteristics (drives backup/restore duration
  independent of row count).
- Real host reboot time, if that specific failure is ever exercised.

None of these can be estimated more precisely from this repository alone
— they are listed here as explicit unknowns rather than guessed at with a
false-precision number.
