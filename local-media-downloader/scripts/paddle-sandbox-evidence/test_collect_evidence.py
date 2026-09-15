"""Tests for the non-network logic in collect_evidence.py. No real HTTP
call is ever made here - every Paddle interaction is a scripted fake, so
these run offline, on this same machine, with `python3 -m pytest`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_evidence as ce


class FakeClient:
    """Scripted stand-in for PaddleClient. `responses` maps
    "METHOD path" -> (status, body), consumed once each (or repeated if
    only one entry exists for a given key)."""

    def __init__(self, responses: dict[str, list[tuple[int, dict]]]):
        self._responses = {k: list(v) for k, v in responses.items()}
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []

    def _pop(self, method: str, path: str) -> tuple[int, dict]:
        key = f"{method} {path}"
        queue = self._responses.get(key)
        if not queue:
            raise AssertionError(f"No scripted response left for {key}")
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def get(self, path: str, params: dict | None = None) -> tuple[int, dict]:
        self.calls.append(("GET", path, params, None))
        return self._pop("GET", path)

    def post(self, path: str, body: dict | None = None) -> tuple[int, dict]:
        self.calls.append(("POST", path, None, body))
        return self._pop("POST", path)

    def patch(self, path: str, body: dict) -> tuple[int, dict]:
        self.calls.append(("PATCH", path, None, body))
        return self._pop("PATCH", path)


# --- masking / env parsing ---------------------------------------------------

def test_mask_short_secret_fully_hidden():
    assert ce._mask("abc") == "***"


def test_mask_long_secret_shows_only_ends():
    masked = ce._mask("sdbx_abcdef1234567890")
    assert masked.startswith("sdbx")
    assert masked.endswith("7890")
    assert "abcdef123456" not in masked


def test_mask_empty():
    assert ce._mask("") == "(empty)"


def test_parse_env_file(tmp_path):
    p = tmp_path / ".env"
    p.write_text('PADDLE_API_KEY=abc123\n# comment\nEMPTY=\nQUOTED="value with spaces"\n')
    values = ce._parse_env_file(p)
    assert values["PADDLE_API_KEY"] == "abc123"
    assert values["QUOTED"] == "value with spaces"
    assert "comment" not in values


def test_parse_env_file_missing_file_returns_empty(tmp_path):
    assert ce._parse_env_file(tmp_path / "does-not-exist.env") == {}


# --- credential loading precedence ------------------------------------------

def test_load_api_key_prefers_environment_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("PADDLE_API_KEY", "from-env-var")
    monkeypatch.setattr(ce, "LOCAL_ENV_PATH", tmp_path / "local.env")
    monkeypatch.setattr(ce, "LOADY_ENV_PATH", tmp_path / "loady.env")
    assert ce.load_api_key(prompt=lambda _: pytest.fail("must not prompt")) == "from-env-var"


def test_load_api_key_falls_back_to_local_env(monkeypatch, tmp_path):
    monkeypatch.delenv("PADDLE_API_KEY", raising=False)
    local_env = tmp_path / "local.env"
    local_env.write_text("PADDLE_API_KEY=from-local-env\n")
    monkeypatch.setattr(ce, "LOCAL_ENV_PATH", local_env)
    monkeypatch.setattr(ce, "LOADY_ENV_PATH", tmp_path / "loady.env")
    assert ce.load_api_key(prompt=lambda _: pytest.fail("must not prompt")) == "from-local-env"


def test_load_api_key_falls_back_to_loady_env_read_only(monkeypatch, tmp_path):
    monkeypatch.delenv("PADDLE_API_KEY", raising=False)
    loady_env = tmp_path / "loady.env"
    loady_env.write_text("PADDLE_API_KEY=from-loady-env\nOTHER=x\n")
    monkeypatch.setattr(ce, "LOCAL_ENV_PATH", tmp_path / "local.env")
    monkeypatch.setattr(ce, "LOADY_ENV_PATH", loady_env)
    original_contents = loady_env.read_text()
    assert ce.load_api_key(prompt=lambda _: pytest.fail("must not prompt")) == "from-loady-env"
    assert loady_env.read_text() == original_contents, "Loady's own .env must never be modified"


def test_load_api_key_prompts_when_nothing_found_and_can_save(monkeypatch, tmp_path):
    monkeypatch.delenv("PADDLE_API_KEY", raising=False)
    local_env = tmp_path / "local.env"
    monkeypatch.setattr(ce, "LOCAL_ENV_PATH", local_env)
    monkeypatch.setattr(ce, "LOADY_ENV_PATH", tmp_path / "loady.env")
    monkeypatch.setattr("builtins.input", lambda _: "y")
    key = ce.load_api_key(prompt=lambda _: "typed-key-value")
    assert key == "typed-key-value"
    assert ce._parse_env_file(local_env)["PADDLE_API_KEY"] == "typed-key-value"


# --- sandbox verification -----------------------------------------------------

def test_verify_sandbox_rejects_key_without_sandbox_marker():
    def fake_get(path, params=None):
        return 200, {}
    with pytest.raises(ce.SandboxVerificationError, match="does not look like a Paddle Sandbox key"):
        ce._verify_sandbox("live_looking_key_1234", fake_get)


def test_verify_sandbox_rejects_non_200_response():
    def fake_get(path, params=None):
        return 401, {"error": "unauthorized"}
    with pytest.raises(ce.SandboxVerificationError, match="HTTP 401"):
        ce._verify_sandbox("apikey_sdbx_abc123", fake_get)


def test_verify_sandbox_passes_with_valid_key_and_200():
    def fake_get(path, params=None):
        assert path == "/subscriptions"
        return 200, {"data": []}
    ce._verify_sandbox("apikey_sdbx_abc123", fake_get)  # must not raise


# --- subscription cancellation is always scheduled, never immediate ---------

def test_schedule_cancellation_uses_next_billing_period_not_immediately():
    client = FakeClient({"POST /subscriptions/sub_1/cancel": [(200, {"data": {}})]})
    ce.schedule_cancellation_at_period_end(client, "sub_1")
    method, path, _params, body = client.calls[0]
    assert method == "POST"
    assert body == {"effective_from": "next_billing_period"}
    assert body["effective_from"] != "immediately"


def test_restore_subscription_nulls_scheduled_change():
    client = FakeClient({"PATCH /subscriptions/sub_1": [(200, {"data": {}})]})
    ce.restore_subscription(client, "sub_1")
    method, path, _params, body = client.calls[0]
    assert method == "PATCH"
    assert body == {"scheduled_change": None}


# --- event polling -------------------------------------------------------------

def test_poll_for_event_returns_matching_event_immediately():
    client = FakeClient({
        "GET /events": [(200, {"data": [{"data": {"id": "sub_1", "scheduled_change": {"action": "cancel"}}}]})],
    })
    event = ce.poll_for_event(client, "subscription.updated", matches=lambda e: e["data"]["id"] == "sub_1", sleep=lambda s: None)
    assert event is not None
    assert event["data"]["id"] == "sub_1"


def test_poll_for_event_times_out_and_returns_none_without_real_sleep():
    calls = {"n": 0}

    def fake_clock():
        calls["n"] += 1
        return calls["n"] * 100.0  # jumps straight past any timeout after one iteration

    client = FakeClient({"GET /events": [(200, {"data": []})]})
    sleeps: list[float] = []
    event = ce.poll_for_event(
        client, "subscription.updated", matches=lambda e: True,
        timeout_s=1.0, sleep=lambda s: sleeps.append(s), clock=fake_clock,
    )
    assert event is None
    assert sleeps == [], "must not have slept once the deadline was already passed"


# --- refund adjustment discovery ---------------------------------------------

def test_find_recent_refund_adjustment_filters_and_sorts(monkeypatch):
    client = FakeClient({
        "GET /adjustments": [(200, {"data": [
            {"id": "adj_old", "action": "refund", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "adj_credit", "action": "credit", "created_at": "2026-01-03T00:00:00Z"},
            {"id": "adj_new", "action": "refund", "created_at": "2026-01-02T00:00:00Z"},
        ]})],
    })
    adjustment = ce.find_recent_refund_adjustment(client)
    assert adjustment["id"] == "adj_new"


def test_find_recent_refund_adjustment_none_when_no_refunds():
    client = FakeClient({"GET /adjustments": [(200, {"data": [{"id": "adj_1", "action": "credit", "created_at": "x"}]})]})
    assert ce.find_recent_refund_adjustment(client) is None


# --- chargeback simulation investigation -------------------------------------

def test_chargeback_simulation_not_found_is_documentation_only():
    client = FakeClient({
        "GET /simulation-types": [(200, {"data": [{"name": "subscription_creation", "description": "..."}]})],
    })
    evidence = ce.investigate_chargeback_simulation(client)
    assert evidence.label == ce.DOCUMENTATION_ONLY
    assert "No chargeback" in evidence.note


def test_chargeback_simulation_found_but_no_destination_is_documentation_only():
    client = FakeClient({
        "GET /simulation-types": [(200, {"data": [{"name": "chargeback_created", "description": "A chargeback"}]})],
        "GET /notification-settings": [(200, {"data": []})],
    })
    evidence = ce.investigate_chargeback_simulation(client)
    assert evidence.label == ce.DOCUMENTATION_ONLY
    assert "no notification destination" in evidence.note.lower()


def test_chargeback_simulation_created_is_labelled_simulator_event():
    client = FakeClient({
        "GET /simulation-types": [(200, {"data": [{"name": "chargeback_created", "description": "A chargeback"}]})],
        "GET /notification-settings": [(200, {"data": [{"id": "ntfset_1"}]})],
        "POST /simulations": [(201, {"data": {"id": "sim_1"}})],
    })
    evidence = ce.investigate_chargeback_simulation(client)
    assert evidence.label == ce.PADDLE_SIMULATOR_EVENT
    assert evidence.payload["simulation"]["id"] == "sim_1"


def test_chargeback_simulation_create_failure_stays_documentation_only():
    client = FakeClient({
        "GET /simulation-types": [(200, {"data": [{"name": "chargeback_created", "description": "A chargeback"}]})],
        "GET /notification-settings": [(200, {"data": [{"id": "ntfset_1"}]})],
        "POST /simulations": [(422, {"error": "bad request"})],
    })
    evidence = ce.investigate_chargeback_simulation(client)
    assert evidence.label == ce.DOCUMENTATION_ONLY
    assert "Create-simulation call failed" in evidence.note


# --- report never leaks the real key -----------------------------------------

def test_report_json_never_contains_the_raw_key():
    report = ce.Report(generated_at="t", sandbox_base_url=ce.SANDBOX_BASE_URL, api_key_masked=ce._mask("sdbx_supersecretvalue"))
    payload = json.dumps(report.to_json())
    assert "supersecretvalue" not in payload


# --- full run() orchestration, fully faked network -----------------------------

def test_run_restores_subscription_even_when_event_poll_times_out(monkeypatch, tmp_path):
    monkeypatch.setenv("PADDLE_API_KEY", "apikey_sdbx_abc123")
    monkeypatch.delenv("PADDLE_TEST_SUBSCRIPTION_ID", raising=False)

    client = FakeClient({
        "GET /subscriptions": [(200, {"data": [{"id": "sub_1", "scheduled_change": None}]})],
        "POST /subscriptions/sub_1/cancel": [(200, {"data": {}})],
        "GET /events": [(200, {"data": []})],  # never matches -> poll times out
        "PATCH /subscriptions/sub_1": [(200, {"data": {}})],
        "GET /subscriptions/sub_1": [(200, {"data": {"id": "sub_1", "scheduled_change": None}})],
        "GET /adjustments": [(200, {"data": []})],
        "GET /simulation-types": [(200, {"data": []})],
    })

    ticks = {"n": 0}

    def fake_clock():
        ticks["n"] += 1
        return ticks["n"] * 1000.0  # past any timeout after the first check

    report = ce.run(sleep=lambda s: None, clock=fake_clock, client_factory=lambda _key: client)

    restore_calls = [c for c in client.calls if c[0] == "PATCH" and c[1] == "/subscriptions/sub_1"]
    assert len(restore_calls) == 1, "restore must be attempted even though the event poll timed out"
    assert any("did not see a matching" in w for w in report.warnings)


def test_run_captures_real_subscription_updated_event(monkeypatch):
    monkeypatch.setenv("PADDLE_API_KEY", "apikey_sdbx_abc123")
    monkeypatch.delenv("PADDLE_TEST_SUBSCRIPTION_ID", raising=False)

    matching_event = {"event_type": "subscription.updated", "data": {"id": "sub_1", "scheduled_change": {"action": "cancel"}}}
    client = FakeClient({
        "GET /subscriptions": [(200, {"data": [{"id": "sub_1", "scheduled_change": None}]})],
        "POST /subscriptions/sub_1/cancel": [(200, {"data": {}})],
        "GET /events": [(200, {"data": [matching_event]})],
        "PATCH /subscriptions/sub_1": [(200, {"data": {}})],
        "GET /subscriptions/sub_1": [(200, {"data": {"id": "sub_1", "scheduled_change": None}})],
        "GET /adjustments": [(200, {"data": []})],
        "GET /simulation-types": [(200, {"data": []})],
    })

    report = ce.run(sleep=lambda s: None, client_factory=lambda _key: client)

    real_events = [e for e in report.evidence if e.label == ce.REAL_SANDBOX_EVENT]
    assert any(e.payload == matching_event for e in real_events)
