#!/usr/bin/env python3
"""Operator-side Paddle Sandbox evidence collector (Mission 13).

Runs on YOUR machine, where Paddle is reachable - this repo's own Claude
Code sessions have no network path to any paddle.com host at all, which is
exactly why this script exists as something you run locally instead of
being asked to click through the Sandbox dashboard by hand.

What it does, in order, ALL against https://sandbox-api.paddle.com (never
configurable to point anywhere else - see `_verify_sandbox`):

  1. Loads your Paddle Sandbox API key from (in order): the
     PADDLE_API_KEY environment variable, this script's own local `.env`
     (gitignored), Loady's existing `backend/.env` (read-only - never
     modified), or a hidden terminal prompt if none of those have it.
  2. PROVES the key/host pair is really Sandbox before touching anything -
     aborts otherwise (see `_verify_sandbox`).
  3. Finds an active subscription, schedules its cancellation at the next
     billing period (reversible - NOT an immediate cancel), polls Paddle's
     own Events API for the genuine `subscription.updated` event this
     produces, then immediately reverses the scheduled change and confirms
     the subscription is back to its original state.
  4. Looks up the refund adjustment you already captured evidence for and
     checks whether Paddle's ~10-minute Sandbox auto-approval has flipped
     it from `pending_approval` to `approved` yet, capturing the real
     `adjustment.updated` event if so.
  5. Investigates (read-only) whether Paddle's Simulations API offers a
     chargeback-shaped scenario, and if so, attempts to generate and
     capture one - clearly labelled as simulator output, never treated as
     equivalent to a real dispute.
  6. Writes a single sanitized JSON report - real API keys/tokens/secrets
     are NEVER written to it or printed to the terminal, only masked
     (last 4 characters).

Every finding in the report is labelled exactly one of:
  REAL_SANDBOX_EVENT     - a genuine event Paddle generated from a real
                            action this script (or you) actually took.
  PADDLE_SIMULATOR_EVENT - Paddle-signed, Paddle-server-generated, but
                            from the Simulations API, not a real lifecycle
                            transition - demo/placeholder field values.
  DOCUMENTATION_ONLY     - nothing captured; only public Paddle docs
                            inform this line, stated as such.

Stdlib only - no `pip install` needed. Run with:
    python3 collect_evidence.py
"""
from __future__ import annotations

import getpass
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SANDBOX_BASE_URL = "https://sandbox-api.paddle.com"
_SANDBOX_KEY_MARKER = "_sdbx"

SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_ENV_PATH = SCRIPT_DIR / ".env"
EVIDENCE_DIR = SCRIPT_DIR / "evidence"
# Loady's own backend/.env, three levels up from this script
# (scripts/paddle-sandbox-evidence/collect_evidence.py -> local-media-downloader/backend/.env)
LOADY_ENV_PATH = SCRIPT_DIR.parent.parent / "backend" / ".env"

REAL_SANDBOX_EVENT = "REAL_SANDBOX_EVENT"
PADDLE_SIMULATOR_EVENT = "PADDLE_SIMULATOR_EVENT"
DOCUMENTATION_ONLY = "DOCUMENTATION_ONLY"

_CHARGEBACK_KEYWORDS = ("chargeback", "dispute")


class SandboxVerificationError(RuntimeError):
    """Raised when this script cannot PROVE it is talking to Paddle
    Sandbox - the caller must abort, never proceed on a guess."""


class PaddleApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body_excerpt: str):
        super().__init__(f"{method} {path} -> HTTP {status}: {body_excerpt}")
        self.status = status


def _mask(secret: str) -> str:
    """Never logs/reports a usable secret - only enough to let a human
    confirm they're looking at the key they expect."""
    if not secret:
        return "(empty)"
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_api_key(prompt: Callable[[str], str] = getpass.getpass) -> str:
    """Search order: real env var -> this script's own .env -> Loady's
    existing backend/.env (read-only, never rewritten) -> hidden terminal
    prompt. Never prints the value it finds."""
    env_key = os.environ.get("PADDLE_API_KEY", "").strip()
    if env_key:
        print(f"Using PADDLE_API_KEY from the environment ({_mask(env_key)}).")
        return env_key

    local_values = _parse_env_file(LOCAL_ENV_PATH)
    if local_values.get("PADDLE_API_KEY"):
        key = local_values["PADDLE_API_KEY"].strip()
        print(f"Using PADDLE_API_KEY from {LOCAL_ENV_PATH} ({_mask(key)}).")
        return key

    loady_values = _parse_env_file(LOADY_ENV_PATH)
    if loady_values.get("PADDLE_API_KEY"):
        key = loady_values["PADDLE_API_KEY"].strip()
        print(f"Reusing PADDLE_API_KEY already configured in {LOADY_ENV_PATH} ({_mask(key)}).")
        return key

    print("No PADDLE_API_KEY found in the environment or existing .env files.")
    key = prompt("Paste your Paddle SANDBOX API key (input hidden, never sent anywhere but Paddle): ").strip()
    if not key:
        raise SandboxVerificationError("No API key provided.")
    save = input(f"Save it to {LOCAL_ENV_PATH} (gitignored, mode 600) for next time? [y/N] ").strip().lower()
    if save == "y":
        _write_local_env({"PADDLE_API_KEY": key})
        print(f"Saved to {LOCAL_ENV_PATH} (permissions restricted to your user only).")
    return key


def _write_local_env(values: dict[str, str]) -> None:
    existing = _parse_env_file(LOCAL_ENV_PATH)
    existing.update(values)
    LOCAL_ENV_PATH.write_text("".join(f"{k}={v}\n" for k, v in existing.items()))
    os.chmod(LOCAL_ENV_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600 - owner read/write only


def _verify_sandbox(api_key: str, http_get: Callable[..., tuple[int, Any]]) -> None:
    """Two independent checks must BOTH pass before any mutation is ever
    attempted. Either one failing aborts the whole run - this is
    deliberately not a warning."""
    if not api_key or _SANDBOX_KEY_MARKER not in api_key:
        raise SandboxVerificationError(
            f"This key does not look like a Paddle Sandbox key (expected to contain "
            f"'{_SANDBOX_KEY_MARKER}', per Paddle's own documented sandbox key format). "
            "Refusing to proceed - this script will NEVER touch a Live key."
        )
    status, _body = http_get("/subscriptions", params={"per_page": "1"})
    if status != 200:
        raise SandboxVerificationError(
            f"A read-only request to {SANDBOX_BASE_URL}/subscriptions returned HTTP {status}, "
            "not 200 - cannot prove this key authenticates against Sandbox. Aborting."
        )
    print(f"Sandbox verification passed: key format matches, and {SANDBOX_BASE_URL} accepted it.")


@dataclass
class Evidence:
    label: str  # REAL_SANDBOX_EVENT | PADDLE_SIMULATOR_EVENT | DOCUMENTATION_ONLY
    what: str
    source: str
    captured_at: str
    payload: dict[str, Any] | None = None
    note: str | None = None


@dataclass
class Report:
    generated_at: str
    sandbox_base_url: str
    api_key_masked: str
    evidence: list[Evidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "sandbox_base_url": self.sandbox_base_url,
            "api_key_masked": self.api_key_masked,
            "evidence": [
                {
                    "label": e.label, "what": e.what, "source": e.source,
                    "captured_at": e.captured_at, "payload": e.payload, "note": e.note,
                }
                for e in self.evidence
            ],
            "warnings": self.warnings,
        }


class PaddleClient:
    """Thin stdlib HTTP wrapper. `http_get`/`http_request` are the only
    seams tests patch - no `requests` dependency, so the one command the
    operator runs never needs `pip install` first."""

    def __init__(self, api_key: str, base_url: str = SANDBOX_BASE_URL):
        self.api_key = api_key
        self.base_url = base_url

    def request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> tuple[int, Any]:
        url = self.base_url + path
        if params:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(params)}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = {"raw": raw[:500]}
            return exc.code, parsed
        except urllib.error.URLError as exc:
            raise PaddleApiError(method, path, 0, f"network error: {exc.reason}") from exc

    def get(self, path: str, params: dict | None = None) -> tuple[int, Any]:
        return self.request("GET", path, params=params)

    def post(self, path: str, body: dict | None = None) -> tuple[int, Any]:
        return self.request("POST", path, body=body or {})

    def patch(self, path: str, body: dict) -> tuple[int, Any]:
        return self.request("PATCH", path, body=body)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_active_subscription(client: PaddleClient) -> dict | None:
    preferred_id = os.environ.get("PADDLE_TEST_SUBSCRIPTION_ID", "").strip()
    if preferred_id:
        status, body = client.get(f"/subscriptions/{preferred_id}")
        if status == 200:
            return body.get("data")
        print(f"PADDLE_TEST_SUBSCRIPTION_ID={preferred_id} could not be fetched (HTTP {status}) - falling back to auto-discovery.")

    status, body = client.get("/subscriptions", params={"status": "active", "per_page": "10"})
    if status != 200:
        return None
    items = body.get("data") or []
    return items[0] if items else None


def schedule_cancellation_at_period_end(client: PaddleClient, subscription_id: str) -> tuple[int, Any]:
    """NEVER 'immediately' - only a scheduled, reversible change. Paddle
    creates `scheduled_change` on the subscription and leaves `status`
    untouched (still active) until the real period end, which is why this
    is safe to do against a real Sandbox subscription and safe to reverse
    a moment later."""
    return client.post(f"/subscriptions/{subscription_id}/cancel", {"effective_from": "next_billing_period"})


def restore_subscription(client: PaddleClient, subscription_id: str) -> tuple[int, Any]:
    """The one documented way to undo a scheduled change short of letting
    it actually happen: null it out."""
    return client.patch(f"/subscriptions/{subscription_id}", {"scheduled_change": None})


def poll_for_event(
    client: PaddleClient,
    event_type: str,
    matches: Callable[[dict], bool],
    timeout_s: float = 45.0,
    interval_s: float = 3.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict | None:
    """Polls Paddle's own Events API (never the local webhook destination)
    for a real event matching `matches`. Returns the full event dict
    (including `.data`, the actual payload) or None on timeout - never
    raises on a mere timeout, since "not there yet" is an expected,
    reportable outcome, not a bug."""
    deadline = clock() + timeout_s
    while True:
        status, body = client.get("/events", params={"event_type": event_type, "per_page": "50", "order_by": "id[DESC]"})
        if status == 200:
            for event in body.get("data") or []:
                if matches(event):
                    return event
        if clock() >= deadline:
            return None
        sleep(interval_s)


def find_recent_refund_adjustment(client: PaddleClient) -> dict | None:
    status, body = client.get("/adjustments", params={"per_page": "50"})
    if status != 200:
        return None
    candidates = [a for a in (body.get("data") or []) if a.get("action") == "refund"]
    if not candidates:
        return None
    candidates.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    return candidates[0]


def investigate_chargeback_simulation(client: PaddleClient) -> Evidence:
    """Read-only discovery first (`/simulation-types`), then a best-effort
    attempt to actually generate one IF Paddle's catalog offers a
    chargeback-shaped scenario. The create/run/fetch leg of the
    Simulations API could not be verified against real docs from this
    session's own network-blocked environment, so failures here are
    reported plainly, never papered over, and NEVER produce a fabricated
    payload - see the module docstring."""
    status, body = client.get("/simulation-types")
    if status != 200:
        return Evidence(
            label=DOCUMENTATION_ONLY, what="chargeback simulation support",
            source="Paddle Simulation Types API", captured_at=_now_iso(),
            note=f"Could not list simulation types (HTTP {status}) - support unconfirmed.",
        )
    types = body.get("data") or []
    matches = [
        t for t in types
        if any(kw in (t.get("name", "") + " " + t.get("description", "")).lower() for kw in _CHARGEBACK_KEYWORDS)
    ]
    if not matches:
        return Evidence(
            label=DOCUMENTATION_ONLY, what="chargeback simulation support",
            source="Paddle Simulation Types API", captured_at=_now_iso(),
            note="No chargeback/dispute-named simulation type found in this account's catalog.",
        )

    chosen = matches[0]
    dest_status, dest_body = client.get("/notification-settings")
    destinations = (dest_body.get("data") or []) if dest_status == 200 else []
    if not destinations:
        return Evidence(
            label=DOCUMENTATION_ONLY, what=f"chargeback simulation type '{chosen.get('name')}' exists",
            source="Paddle Simulation Types API", captured_at=_now_iso(),
            payload={"simulation_type": chosen},
            note="A matching simulation type exists, but no notification destination was found to run it against.",
        )

    sim_status, sim_body = client.post("/simulations", {
        "notification_setting_id": destinations[0].get("id"),
        "name": "mission-13-chargeback-shape-check",
        "type": chosen.get("name"),
    })
    if sim_status not in (200, 201):
        return Evidence(
            label=DOCUMENTATION_ONLY, what=f"attempted to create a '{chosen.get('name')}' simulation",
            source="Paddle Simulations API", captured_at=_now_iso(),
            payload={"simulation_type": chosen},
            note=f"Create-simulation call failed (HTTP {sim_status}): {json.dumps(sim_body)[:300]}",
        )

    simulation = sim_body.get("data") or {}
    return Evidence(
        label=PADDLE_SIMULATOR_EVENT, what=f"'{chosen.get('name')}' simulation created",
        source="Paddle Simulations API", captured_at=_now_iso(),
        payload={"simulation_type": chosen, "simulation": simulation},
        note=(
            "Simulation created successfully. Retrieving the generated event payload's exact "
            "shape could not be verified against Paddle's docs from this session (network-blocked) - "
            "check the Sandbox dashboard's Notifications > Simulate log for this simulation's run to "
            "see the generated payload, or re-run this script once that leg is confirmed."
        ),
    )


def run(
    prompt: Callable[[str], str] = getpass.getpass,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    client_factory: Callable[[str], "PaddleClient"] = PaddleClient,
) -> Report:
    report = Report(generated_at=_now_iso(), sandbox_base_url=SANDBOX_BASE_URL, api_key_masked="")
    api_key = load_api_key(prompt)
    report.api_key_masked = _mask(api_key)
    client = client_factory(api_key)

    _verify_sandbox(api_key, client.get)

    # --- 1. subscription.updated via a real, reversible scheduled cancellation ---
    subscription = find_active_subscription(client)
    if subscription is None:
        report.warnings.append("No active Sandbox subscription found - skipped subscription.updated capture.")
    else:
        sub_id = subscription["id"]
        baseline_scheduled_change = subscription.get("scheduled_change")
        print(f"Scheduling a cancel-at-period-end on {sub_id} (reversible)...")
        cancel_status, cancel_body = schedule_cancellation_at_period_end(client, sub_id)
        if cancel_status not in (200, 201):
            report.warnings.append(f"Could not schedule cancellation on {sub_id} (HTTP {cancel_status}).")
        else:
            try:
                print("Polling Paddle's Events API for the real subscription.updated event...")
                event = poll_for_event(
                    client, "subscription.updated",
                    matches=lambda e: (e.get("data") or {}).get("id") == sub_id and (e.get("data") or {}).get("scheduled_change"),
                    sleep=sleep, clock=clock,
                )
                if event is not None:
                    report.evidence.append(Evidence(
                        label=REAL_SANDBOX_EVENT, what="subscription.updated (scheduled cancellation)",
                        source="Paddle Events API", captured_at=_now_iso(), payload=event,
                    ))
                    print("Captured a real subscription.updated event.")
                else:
                    report.warnings.append(
                        f"Scheduled the cancellation on {sub_id} but did not see a matching "
                        "subscription.updated event within the poll window."
                    )
            finally:
                print(f"Restoring {sub_id} to its original state...")
                restore_status, _ = restore_subscription(client, sub_id)
                verify_status, verify_body = client.get(f"/subscriptions/{sub_id}")
                restored_ok = (
                    restore_status in (200, 201)
                    and verify_status == 200
                    and (verify_body.get("data") or {}).get("scheduled_change") == baseline_scheduled_change
                )
                if not restored_ok:
                    report.warnings.append(
                        f"RESTORE MAY HAVE FAILED for subscription {sub_id} - please check it manually "
                        "in the Sandbox dashboard. This is the one thing this script cannot silently retry."
                    )
                else:
                    print(f"Confirmed {sub_id} is back to its original scheduled_change state.")

    # --- 2. adjustment.updated for the already-known refund, if Sandbox has auto-approved it ---
    adjustment = find_recent_refund_adjustment(client)
    if adjustment is None:
        report.warnings.append("No refund-action adjustment found on this account - skipped adjustment.updated capture.")
    else:
        adj_status = adjustment.get("status")
        if adj_status != "approved":
            report.evidence.append(Evidence(
                label=DOCUMENTATION_ONLY, what="refund adjustment approval status",
                source="Paddle Adjustments API", captured_at=_now_iso(),
                payload={"adjustment_id": adjustment.get("id"), "status": adj_status},
                note=(
                    f"Most recent refund adjustment is still '{adj_status}', not yet 'approved' "
                    "(Sandbox auto-approves roughly every 10 minutes after creation) - re-run this "
                    "script in a few minutes to capture the real adjustment.updated event."
                ),
            ))
        else:
            event = poll_for_event(
                client, "adjustment.updated",
                matches=lambda e: (e.get("data") or {}).get("id") == adjustment.get("id"),
                timeout_s=15.0, sleep=sleep, clock=clock,
            )
            if event is not None:
                report.evidence.append(Evidence(
                    label=REAL_SANDBOX_EVENT, what="adjustment.updated (refund approved)",
                    source="Paddle Events API", captured_at=_now_iso(), payload=event,
                ))
                print("Captured a real adjustment.updated (approved) event.")
            else:
                report.evidence.append(Evidence(
                    label=REAL_SANDBOX_EVENT, what="adjustment resource (approved, event not found in feed)",
                    source="Paddle Adjustments API", captured_at=_now_iso(),
                    payload={"adjustment": adjustment},
                    note="The adjustment resource itself shows status=approved; the corresponding "
                         "adjustment.updated event was not found in the Events API feed within the poll window.",
                ))

    # --- 3. chargeback/dispute simulation support (read-only investigation + best-effort capture) ---
    report.evidence.append(investigate_chargeback_simulation(client))

    return report


def main() -> int:
    try:
        report = run()
    except SandboxVerificationError as exc:
        print(f"\nABORTED - sandbox verification failed: {exc}", file=sys.stderr)
        return 2
    except PaddleApiError as exc:
        print(f"\nABORTED - Paddle API error: {exc}", file=sys.stderr)
        return 3

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVIDENCE_DIR / f"paddle-sandbox-evidence-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report.to_json(), indent=2, default=str))

    print("\n=== Summary ===")
    for e in report.evidence:
        print(f"[{e.label}] {e.what} (via {e.source})")
        if e.note:
            print(f"    note: {e.note}")
    if report.warnings:
        print("\nWarnings:")
        for w in report.warnings:
            print(f"  - {w}")
    print(f"\nFull sanitized report written to: {out_path}")
    print("Send that file back (or paste its contents) for the code audit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
