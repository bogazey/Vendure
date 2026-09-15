# Paddle Sandbox evidence collector (Mission 13)

Run this **on your Mac**, where Paddle is actually reachable — the Claude
Code session that built this has no network path to any `paddle.com` host
at all (confirmed: even public docs are proxy-blocked from there), so this
script exists to do the Sandbox work locally instead of asking you to
click through the dashboard by hand.

## What it does

Against `https://sandbox-api.paddle.com` only — never configurable to
point anywhere else, and it verifies the key/host pair really is Sandbox
before touching anything (aborts otherwise, see `_verify_sandbox` in
`collect_evidence.py`):

1. Finds an active Sandbox subscription, schedules its cancellation at
   the next billing period (**reversible** — never an immediate cancel),
   polls Paddle's own Events API for the real `subscription.updated`
   event this produces, then immediately un-schedules the cancellation
   and confirms the subscription is back to normal.
2. Checks whether the refund you already captured evidence for has been
   auto-approved yet (Sandbox does this automatically, roughly every 10
   minutes) and captures the real `adjustment.updated` event if so.
3. Checks (read-only) whether Paddle's Simulations API offers a
   chargeback-shaped scenario for this account, and if so, attempts to
   generate one — clearly labelled as simulator output, never treated as
   a real dispute.

Every finding is labelled exactly one of:

- `REAL_SANDBOX_EVENT` — a genuine event from a real action.
- `PADDLE_SIMULATOR_EVENT` — Paddle-generated, but from the Simulator, not
  a real lifecycle transition.
- `DOCUMENTATION_ONLY` — nothing was captured; stated as such.

## Run it

```
python3 collect_evidence.py
```

No `pip install` needed — standard library only. Requires Python 3.9+
(macOS ships this, or `brew install python3` if not).

You'll be prompted for your Paddle **Sandbox** API key if it isn't already
found via (checked in order) the `PADDLE_API_KEY` environment variable,
this directory's own `.env` (offered after the prompt, gitignored, saved
mode `600`), or your existing `local-media-downloader/backend/.env` (read
from, never modified). The key is never printed — only masked
(`sdbx...ab12`) — and this script only ever sends it to
`sandbox-api.paddle.com`.

Optional: set `PADDLE_TEST_SUBSCRIPTION_ID` if you want a specific
subscription used instead of auto-discovery (the first active one found).

## Output

A sanitized JSON report at `evidence/paddle-sandbox-evidence-<timestamp>.json`
(gitignored — this directory's contents are never committed). Send that
file back for the code audit. It contains real business data (subscription
IDs, statuses, timestamps, amounts) — that's the evidence — but never a
secret: no API key, webhook secret, or Authorization header value is ever
written to it or printed to your terminal.

## Tests (no network, safe to run anytime)

```
python3 -m pytest test_collect_evidence.py -v
```

All 25 tests run against a fully scripted fake Paddle client — nothing
here ever makes a real HTTP call.

## Safety

- Sandbox only — the base URL is hardcoded, and a sandbox key
  (`_sdbx`-marked) plus a live 200 response from Sandbox are both required
  before any mutation is attempted.
- The only two mutations this script ever performs are scheduling a
  cancel-at-period-end and un-scheduling it — no plan changes, no
  deletions, no customer data changes, no immediate cancellation.
- The restore step runs in a `finally` block — it's attempted even if
  event capture fails or times out, and the report says plainly if
  restoration could not be confirmed.
- Never touches Paddle Live, production, DNS, Cloudflare, the VPS, or any
  production database — none of those are reachable from this script by
  design (it only ever calls `sandbox-api.paddle.com`).
