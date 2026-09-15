# Alert Thresholds (Mission 15, Phase 42)

Every signal from `POST_MIGRATION_MONITORING.md`, classified into
rollback-triggering vs. investigate-only, with a practical threshold that
avoids paging someone over an isolated typo or a single transient blip.

| Signal | Investigate-only threshold | Rollback-triggering threshold |
|---|---|---|
| `/health`/`/ready` failures | A single non-200 (could be a deploy blip) | 3+ consecutive failed polls (30-45s of sustained downtime), or any failure lasting past the next scheduled poll after a retry |
| Login failure rate | A single isolated failure per unique account | A sustained rate above the pre-cutover baseline for more than 5 minutes, or **any** `ForbiddenError` ("already linked to a different identity") — even one, since this indicates a genuine account-collision bug, not noise |
| OAuth callback failures | A single PKCE/state mismatch (can happen from a stale browser tab) | A cluster of failures for the same client_id/redirect combination — indicates a config problem, not user error |
| Refresh failures | Occasional (an expired/revoked token is normal) | A rate spike coinciding with the cutover window specifically |
| Download authorization failures | Isolated per-account | A rise concentrated on **migrated accounts specifically**, cross-checked against Platform Core health first (a real Platform Core outage explains it without being a bug) |
| 5xx rate (either service) | A single request | Any sustained rise correlated with the cutover window |
| `payment_records` count | N/A — this must never move for reasons unrelated to a known real Paddle event | **Any** unexplained increase — always a rollback trigger, never merely "investigate," since identity migration has zero legitimate reason to touch this table |
| Central-disable propagation | A single check outside the ~5-minute SLA window (timing has some natural jitter) | A change of access **not** propagating within roughly 2x the measured SLA (~10 minutes) on repeat checks |
| Gifted entitlement changes with a null/unexpected actor | N/A | **Any** occurrence — always a security review trigger, not a volume-based threshold |
| Reconciliation | N/A | Any single `FAIL` — Phase 31's invariants are pass/fail, not thresholded |
| Webhook failures (`billing_webhook_events.status='failed'`, only if billing cutover in scope) | 1-2 isolated failures (could be a single malformed test event) | A rising count over more than one polling interval, or any failure on an `adjustment.*` event specifically (money-affecting) |
| Outbox backlog | A small, shrinking backlog (retries in progress) | A backlog that is flat or growing across two consecutive checks past `outbox_max_attempts` × `outbox_delivery_timeout_seconds` |
| Admin errors concentrated on one account | A single error (could be a genuine one-off misuse attempt, expected to be denied) | Multiple errors specifically probing role/product boundaries — cross-check against `test_admin.py`'s scoping invariant, which real production data should never violate |

## Principle used throughout

A threshold is rollback-triggering only where
`ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md` already lists the
underlying condition as an explicit trigger — this table does not invent
new rollback conditions, it only adds the *practical volume/frequency*
distinction (isolated vs. sustained) that a raw binary trigger list
doesn't specify on its own. Anything not on the objective trigger list is
capped at investigate-only here, regardless of how alarming it looks in
isolation, to avoid the "alerting on isolated typos" failure mode Phase 42
explicitly warns against.
