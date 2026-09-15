# Paddle Live Cutover Checklist (Mission 15, Phase 15)

**Nothing on this checklist has been performed.** Paddle Live was not
accessed. This operationalizes `PADDLE_LIVE_INPUTS_REQUIRED.md` and
`BILLING_CUTOVER_RUNBOOK.md` (both already written, Missions 10-14) into a
single ordered checklist for the human operator, adding no new decisions —
every item below cites the document that already established it.

## Pre-flight: what must already be true before this checklist starts

- [ ] Mission 3's identity migration complete for every user this cutover
      covers (`BILLING_CUTOVER_RUNBOOK.md` Prerequisite 1).
- [ ] Platform Core running in a real, monitored, Postgres-backed
      environment — this mission's own architecture package
      (`PRODUCTION_ARCHITECTURE_FREEZE.md`) exists to satisfy this, but
      actual deployment is a separate, later, explicitly-authorized action.
- [ ] `PADDLE_WEBHOOK_SECRET` provisioned (Platform Core) — **credential
      blocker**, not requested by this mission.
- [ ] Platform Core's public webhook URL known
      (`https://id.loady.cc/api/v1/billing/webhooks/paddle`, once the
      domain decision in `IDENTITY_DOMAIN_DECISION.md` is finalized).

## Sandbox evidence already closed (do not re-litigate — see `FINAL_PREPRODUCTION_EVIDENCE_AUDIT.md` §3)

| Evidence | Status |
|---|---|
| `adjustment.created` refund, `pending_approval` | SANDBOX VERIFIED (Mission 9) |
| `adjustment.updated`, `approved` (same adjustment) | SANDBOX VERIFIED (Mission 14) |
| Redelivery of the same approved event never double-refunds | SANDBOX VERIFIED + UNIT TEST VERIFIED |
| `subscription.updated` (`current_billing_period`, `scheduled_change`) | SANDBOX VERIFIED (Mission 14) |
| Chargeback/dispute event shape | **LIVE OBSERVATION ONLY** — this Sandbox account's simulator has no chargeback scenario at all (confirmed programmatically, Mission 13); no further Sandbox work can close this |

## Checklist (ordered, matching `BILLING_CUTOVER_RUNBOOK.md`'s stages)

1. [ ] **Stage 1 dry-run** — restore a real production backup into an
   isolated environment, run
   `python -m app.scripts.loady_paddle_reconciliation_dry_run --loady-database-url <restored-snapshot>`.
   Zero `failed`; every `orphaned_subscription` traced to a specific
   not-yet-migrated user (expected, not a bug); zero
   `duplicate_local_reference` (a real Loady data-integrity issue if
   nonzero — investigate before continuing).
2. [ ] **Stage 2a — Sandbox webhook registration** — add Platform Core's
   webhook URL as an *additional* Paddle Sandbox destination (Loady's own
   endpoint keeps running unchanged).
3. [ ] **Stage 2b — Sandbox lifecycle parity** — drive one real Sandbox
   subscription through create/renew/cancel/refund; confirm Platform
   Core's recorded state matches Loady's own trusted webhook handler's
   recorded state for the same events.
4. [ ] **Stage 2c — Live webhook registration** — only after Stage 2b
   passes: repeat as an *additional* destination in Paddle **Live**.
   Loady's own endpoint keeps running unchanged; nothing yet depends on
   Platform Core's copy.
5. [ ] **Stage 3 — commit reconciliation (backfill)** — during a defined
   low-traffic window, against real production data (read-only access is
   sufficient), run the same script with `--commit`. Review the same way
   as Stage 1.
6. [ ] **Stage 4 — 7-day parallel verification window** (Decision #8,
   `PADDLE_LIVE_INPUTS_REQUIRED.md` §5) — both systems live, neither
   authoritative for a decision. Zero unexplained divergence required for
   the *entire* window before proceeding — any divergence is a bug to fix,
   not a business call.
7. [ ] **Stage 5 — cut Loady's own webhook endpoint over** — remove it from
   both Sandbox and Live destinations; Platform Core becomes the sole
   listener. Monitor `BillingWebhookEvent.status = "failed"` closely for
   the first real week.

## Explicit non-goals (Decision #6, unchanged)

- Checkout creation stays on Loady's side for this cutover — Platform
  Core's `PaddleBillingProvider.create_checkout` remains unconfigured, by
  design, throughout every step above.
- No Paddle price IDs are needed for Platform Core's own catalog for this
  cutover.

## Live-only item, restated once more so it is never silently treated as closed

**Chargeback/dispute lifecycle remains `LIVE OBSERVATION ONLY`.** The
existing conservative immediate-revoke-no-grace-period handling
(`PADDLE_LIVE_INPUTS_REQUIRED.md` §5 Decision #1) stands unchanged and
untested against a real dispute event. The first real Live chargeback,
whenever it occurs, is the evidence this can ever be upgraded past
`DOCUMENTED ONLY`/`LIVE OBSERVATION ONLY` — post-cutover monitoring
(Phase 41) must specifically watch for the first such event and treat it
as a priority manual-review trigger, not routine traffic.

## Blocker classification (unchanged from `PADDLE_LIVE_INPUTS_REQUIRED.md` §4a, restated for this mission's Phase 54)

| Item | Classification |
|---|---|
| Chargeback/dispute real event shape | LIVE OBSERVATION ONLY |
| `PADDLE_WEBHOOK_SECRET`, deployed+monitored Platform Core, public webhook URL | CREDENTIAL BLOCKER / INFRASTRUCTURE BLOCKER |
| Read-only production snapshot for Stage 1 | CREDENTIAL BLOCKER |
| Stage 1 → Stage 5 execution itself | PRODUCTION AUTHORIZATION |
| Mission 3 identity migration run against real users | PRODUCTION AUTHORIZATION |
| Code in `paddle_provider.py`/`webhook_service.py`/`subscription_service.py` | **None outstanding** — zero mismatches found across Missions 9/14's audits |
