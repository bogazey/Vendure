# Production Logging Review (Mission 15, Phase 43)

Grepped both codebases for logging calls referencing anything
password/secret/token/api_key/private_key-shaped, then read each match in
context (not just grep-matched, to avoid false-positive-driven
conclusions).

## Genuine defect found and fixed: Platform Core's email service leaked real reset/verification tokens to logs unconditionally

**Finding**: `platform-core/backend/app/services/email_service.py`
unconditionally logged the full verification/password-reset/email-change
URL — including its embedded, security-sensitive token — via
`logger.info`, in every environment, with no gate. Unlike Loady's own
equivalent (`backend/app/services/email_service.py`'s `LogEmailBackend`,
which explicitly checks `app_env != "development"` and falls back to a
redacted message), Platform Core's version had no such check. Compounding
this: `settings.py` declares an `email_backend` field (default `"log"`)
that is **never read anywhere** — there is no alternate backend
implemented, so an operator cannot avoid the leak by "changing
`EMAIL_BACKEND`" as `.env.production.example`'s own comment instructs,
because nothing in the code consults that setting.

**Fix**: `email_service.py`'s three functions now check `app_env` the
same way Loady's already-tested `LogEmailBackend` does — real URL logged
only when `app_env == "development"` (the default, matching what the test
suite already runs under); any other value logs a redacted
`"Email delivery is not configured; suppressed ... email to %s"` message
with no token, mirroring Loady's `DisabledEmailBackend` message shape
exactly.

**Regression test**: `platform-core/backend/tests/test_email_service_redaction.py`
— 4 new tests: development still logs the real URL (proves existing
behavior unchanged), production/staging suppress it for all three
functions (verification, password reset, email change). All 9 tests in
this file plus the existing `test_email_change.py` pass together
(confirmed this mission — `9 passed`).

**Why this qualifies as in-scope under the No Feature Creep rule**: this
is exactly a "genuine production-readiness defect" this mission's own
review discovered — documented, fixed minimally (no new email provider
built, no new configuration surface added, only mirroring an already-
proven pattern from the sibling codebase), with a regression test, and
the full relevant suite re-run green.

## Everything else checked and confirmed already safe

| Area | Finding |
|---|---|
| Password hashes | Never logged anywhere in either codebase (grep confirms only `logger.info("Password reset completed for ... %s", user.id)` — the user id, not the hash) |
| Access/refresh tokens | `platform_identity_service.py`/`platform_entitlement_service.py` log only `type(exc).__name__` on decryption failure, or an HTTP status code on rejection — never the token value itself |
| OAuth client secrets | `PRODUCTION_SECRET_INVENTORY.md` already confirmed: Platform Core stores only a hash, never logs the plaintext at issuance (printed once to the terminal by the registration script, never to a log file) |
| Paddle secrets | `paddle_provider.py`'s `verify_webhook` compares HMAC digests; no log line anywhere prints the webhook secret or a raw signature |
| DB passwords | Never referenced in any `logger.*` call in either codebase (confirmed by the same grep sweep) |
| Signing private key | Never read into a Python string for logging purposes anywhere outside `jwt_keys.py`'s own file-loading code, which never logs its contents |
| Encryption keys | `token_encryption_service.py`'s own error paths log only exception type names, per its established, already-tested pattern |
| Migration report PII | Covered separately in `FINAL_MIGRATION_DRY_RUN_PROCEDURE.md` — real email addresses do appear in CONFLICTED/FAILED/CREATED/LINKED/SKIPPED rows (not a hash/token/secret, but real PII); documented as an operational handling note there, not a code defect |

## Method

`grep -rn "logger\.\(info\|warning\|error\|debug\)(.*\(password\|secret\|token\|api_key\|private_key\)" -i` across
`platform-core/backend/app/` and `backend/app/`, then every match read in
full context (not just the matched line) to distinguish a real value from
a variable/field *name* appearing incidentally in a log message about
something else (e.g. "Stored Platform Core refresh token could not be
decrypted" — the word "token" appears, but no token value does).
