# Maintenance Window Plan (Mission 15, Phase 21)

## Decision: yes, a short maintenance window is used — ratifying, not replacing, the existing design

`LOADY_PRODUCTION_CUTOVER_RUNBOOK.md` (Mission 3/5) already designed and
partially rehearsed this exact window (sections C through N). This mission
does not redesign it — Phase 21's job is to (1) confirm it is still the
right call, (2) fold in the two things that runbook predates: Platform
Core's own deployment as part of the same VPS package, and the Cloudflare
cache-bypass gap this mission found — and (3) carry its content forward
into the Phase 26 final runbook rather than leaving two runbooks that
could drift apart.

**Why a window, not a live/zero-downtime migration**: the identity
migration writes `global_user_id` back into Loady's `users` table for
every account in one commit pass. Doing this against a database receiving
live writes risks a user's record changing between the dry-run read and
the commit write (a real, if narrow, race). A short, explicit maintenance
window (mutations blocked, reads still served) removes this race entirely
at a measured, small cost — the existing runbook's own reasoning, still
sound.

## Expected duration

**10-15 minutes**, per `LOADY_PRODUCTION_CUTOVER_RUNBOOK.md`'s own
estimate, based on real measured staging timings (migration commit +
reconciliation together completed in well under a minute at 51 synthetic
users). Production's real user count will take longer than 51 rows, but
the tool's per-row cost is the same lightweight operation (a handful of
column writes), so this remains a reasonable estimate rather than a wild
guess — **the exact real-world duration at true production scale is
`PRODUCTION PREFLIGHT REQUIRED`** (row count unknown to this mission) and
must be re-estimated once that count is known, before the real window is
scheduled.

## Enable / verify / disable procedure (unchanged mechanism, confirmed still correct)

1. **Enable**: `MAINTENANCE_MODE=true` in Loady's production env, restart
   the backend.
2. **Verify**: `GET /api/health` still returns 200 (health monitoring
   keeps working); any mutating request (`POST`/`PUT`/`PATCH`/`DELETE`)
   returns `503` with `{"code":"MAINTENANCE_MODE"}` and a `Retry-After`
   header — verified live against staging in a prior mission (Mission 5,
   phase 6).
3. **Disable**: `MAINTENANCE_MODE=false`, restart the backend. Verified
   live in a prior mission that a full-stack restart around this flag
   flip leaves every dataset byte-identical (Mission 5, phase 19) — this
   is not a new claim, it is a re-citation of already-live-verified
   behavior.
4. **Stop condition**: if health checks themselves start failing (not just
   mutations being correctly blocked), that is a deploy problem, not a
   maintenance-mode problem — abort and investigate before proceeding
   further into the window.

## What this mission adds: Platform Core's own place in the window

The existing runbook predates a combined single-VPS deployment — it
assumes Platform Core is "already running somewhere." This mission's
Phase 22 sequencing makes explicit what was previously implicit: **Platform
Core must already be deployed, healthy, and independently verified BEFORE
the maintenance window even starts** (its own deployment is not part of
the window at all — see `PRODUCTION_DEPLOYMENT_SEQUENCING.md`). The
maintenance window itself is scoped narrowly to the identity-migration
commit + reconciliation, exactly as the existing runbook already defines
it — this mission does not widen the window to include infrastructure
work that can and should happen earlier, with time to fix problems, not
under a ticking maintenance clock.

## What this mission adds: the Cloudflare cache gap, closed

`FINAL_PREPRODUCTION_EVIDENCE_AUDIT.md` §8 and
`CLOUDFLARE_CUTOVER_PLAN.md`'s cache-exclusions section identify and close
a real gap: nothing in the existing runbook addressed whether Cloudflare
might cache the maintenance-mode HTML response past the window's actual
end, leaving users stuck seeing "under maintenance" after service resumes.
Added as an explicit new sub-step under maintenance start/end:

- **At maintenance start**: confirm (per `CLOUDFLARE_CUTOVER_PLAN.md`) that
  no Cloudflare Cache Rule caches HTML responses for `loady.cc/*` — if one
  exists, either exclude it for the window or be prepared to purge cache
  explicitly at maintenance end.
- **At maintenance end**: if any doubt remains about whether the
  maintenance response was cached, perform a Cloudflare cache purge for
  `loady.cc/*` as the very last step before declaring the window closed,
  and verify via a real fetch (not from a browser with its own cache) that
  the live page — not a cached maintenance page — is served.

## Rollback interaction

Every step inside the window (C through N of the existing runbook) already
has its own `STOP CONDITION`/rollback implication defined — this mission
does not change that structure, only folds it into the Phase 26 final
runbook alongside Platform-Core-specific steps that now precede it.
