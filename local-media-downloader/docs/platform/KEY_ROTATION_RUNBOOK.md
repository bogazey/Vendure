# Key Rotation Runbook (Mission 5, Phase 28)

Manual procedures only — no automatic rotation exists, and none is being
built here (per the mission's own "don't over-engineer" guidance). Every
step below reflects behavior actually observed live during Mission 5's
phase 16/17 signing-key and token-encryption failure-injection testing
against `platform-core-staging`/`loady-staging` — not assumption.

## RS256 signing key rotation (Platform Core)

**What breaks if done carelessly**: every access/session token issued
under the old key becomes unverifiable the instant the key file changes
— confirmed live (swapping in a different key, then swapping back,
correctly rejected a token signed under the "wrong" key with a clean 401,
no algorithm confusion, no crash).

**Recommended procedure (JWKS overlap, not a hard cutover)**:

1. Generate the new key file (`generate-staging-signing-key.sh`'s
   production equivalent), with a **new `kid`** distinct from the current
   one — never reuse a `kid`, since it's how a verifier picks which
   public key to check a token against.
2. Publish **both** keys' public halves via the JWKS endpoint during the
   transition window (structurally supported — `kid` is already embedded
   in every issued token's header and JWKS already serves multiple keys
   by design) so tokens issued under the old key continue verifying
   while the transition is in progress.
3. Switch the signing (private-key) side to the new key — new tokens are
   now issued with the new `kid`.
4. Wait out the **maximum token lifetime** (15 minutes for access
   tokens, 30 days for refresh tokens issued under the OAuth flow) before
   removing the old public key from JWKS — removing it earlier will
   reject still-valid tokens that haven't been refreshed yet.
5. Remove the old key from JWKS and delete the old private key file.

**A real operational gotcha found live, worth stating explicitly**:
never let the signing-key file be briefly *absent* from its mounted path
while a container (re)creation happens. Docker Desktop's bind-mount
handling was observed to silently materialize an **empty directory** at
the missing path, which then has to be manually found and cleaned up
(`rmdir`) even after the real key file is restored — a plain "restore
the file and restart" was not enough; the container had to be fully
removed (`docker compose rm -f` then `up -d`), not just restarted, to
pick up the corrected mount. Always stage the **new** key file at the
mount path first, confirm it's readable, and only then trigger any
container recreation — never remove the old file before the new one is
already in place.

**Fail-closed behavior, confirmed live**: a genuinely missing key file
causes a hard container start failure (not a graceful degraded mode) in
any environment where `APP_ENV != development` — this is intentional
(see `jwt_keys.py`) and was reproduced exactly as documented.

## Token encryption key rotation (Loady's `PLATFORM_TOKEN_ENCRYPTION_KEY`)

**What breaks if done carelessly**: every `PlatformOidcToken` row
encrypted under the old key becomes **permanently** unreadable the moment
the key changes — there is currently **no key-version field on the
envelope** (`v1:<nonce>:<ciphertext>` — the `v1` is an envelope-format
version, not a key version) and no re-encryption-in-place tooling. This
was confirmed live: swapping in a different valid key made every
existing row fail decryption (caught cleanly, logged as an exception type
only, no plaintext/ciphertext/key material ever appeared in logs) with no
automatic recovery once the correct key was restored except that the
*correct* key naturally decrypts its own prior ciphertext again — a truly
*different* replacement key can never recover data encrypted under the
old one.

**Recommended procedure** (no overlap window is possible with the
current single-key design, so this necessarily has a hard cutover
moment):

1. **Before rotating**, force every currently-linked user through the
   OAuth flow again is not required — instead, decrypt-and-re-encrypt
   every existing row while the OLD key is still active:
   - Read every `PlatformOidcToken` row's `access_token`/`refresh_token`
     with the current key.
   - Immediately re-encrypt each with the **new** key and write it back,
     in the same transaction per row (so a failure mid-run leaves
     individual rows either fully old or fully new, never a mix that
     can't be resolved).
   - `app/scripts/encrypt_platform_oidc_tokens.py`'s existing one-time
     migration pattern is the right shape to extend for this — it
     already knows how to iterate every row safely; a rotation variant
     would decrypt-with-old/encrypt-with-new instead of
     plaintext-to-encrypted.
2. Only after every row is confirmed re-encrypted under the new key,
   update `PLATFORM_TOKEN_ENCRYPTION_KEY` in the environment and restart
   Loady's backend.
3. Verify: pick a linked account, confirm a live entitlement check
   succeeds (proves the new key correctly decrypts its own freshly
   re-encrypted row).

**If the old key is lost before this re-encryption step runs**: every
existing `PlatformOidcToken` row is unrecoverable. The safe, if
disruptive, recovery is to delete those rows (never guess or leave
corrupt ciphertext in place indefinitely) — every affected user simply
needs to complete the OAuth linking flow again on their next visit,
which is a normal, already-tested path (Mission 5 phase 10), not a
data-loss incident for anything except the token cache itself (identity,
history, usage, and local entitlement data are untouched — only the
Platform Core session/refresh token cache is lost).

**Recommendation for before this is needed in production**: add a key
**version** prefix to the envelope (e.g. `v1:<key_version>:<nonce>:
<ciphertext>`) so a future rotation can support genuine key overlap
(try the current key, fall back to a short list of recently-retired keys
by version, exactly like the JWKS `kid` mechanism already does for
signing keys). Not built in this mission — tracked as a MEDIUM-severity
follow-up in `PRODUCTION_READINESS_CHECKLIST.md`, not a blocker for an
initial migration (a single planned rotation, done carefully with the
procedure above, does not require it).

## OAuth client secret rotation (`PLATFORM_CLIENT_SECRET`)

**What breaks if done carelessly**: Platform Core only ever stores a
**hash** of the client secret (never the plaintext, by design — see
`oidc_service.register_client`) — there is no "look up the current
secret" recovery path. Rotation is a hard cutover with no overlap: the
new secret must be deployed to Loady in the same maintenance action as
issuing it.

**Recommended procedure**:

1. Generate a new secret for the `loady` OAuth client at Platform Core
   (requires a new script or admin endpoint — `register_loady_client.py`
   only handles first-time registration today; a `rotate_client_secret`
   equivalent does not exist yet, tracked as a follow-up).
2. Update Loady's `PLATFORM_CLIENT_SECRET` and restart its backend in the
   **same maintenance window** — any request in between (token refresh,
   new OAuth login) will fail with an OAuth `invalid_client` error until
   both sides agree.
3. Verify with a real login/refresh cycle immediately after.

This is lower-frequency and lower-risk than the two key rotations above
(a compromised client secret lets an attacker impersonate the Loady
*application* to Platform Core, not forge arbitrary user tokens or read
arbitrary stored data) but should still be rotated on any suspected
compromise or after a config leak.
