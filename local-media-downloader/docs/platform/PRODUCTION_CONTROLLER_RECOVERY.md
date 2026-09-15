# Production Controller Recovery (Mission 16)

## Resume after terminal disconnect (Phase 25)

The controller never depends on one interactive shell staying open. Every
command is a fresh, independent process that reads `state.json`, does its
one job, writes `state.json`, and exits. If the SSH session to the real
VPS drops mid-cutover:

1. Reconnect.
2. Run `platform-production.sh status --environment production`.
3. The output shows exactly which stage last completed and what
   `current_state` is — never "unknown," since every stage transition is
   durably written before the command that caused it returns.
4. Continue with the next command in the sequence. The controller does
   **not** automatically resume or retry a dangerous stage on your
   behalf — you decide, informed by `status`, what to run next.

This is not a theoretical property — `SECTION 9` of
`scripts/platform/test-platform-production.sh` actually sends `SIGTERM`
to a running `migrate` invocation mid-flight and confirms `status`
afterward shows `INTERRUPTED`, not a stale `MAINTENANCE` that would
mislead an operator into thinking nothing happened yet.

## Interruption during each stage (Phase 26)

| Interrupted during | What `status` shows afterward | Safe next action |
|---|---|---|
| `preflight`/`plan`/`status` (read-only) | Unchanged — no state write happens for these unless they complete | Just re-run |
| `backup` | `PREFLIGHT_PASSED` (no stage completion recorded) if killed before the script exits; **`INTERRUPTED`** if killed after `DANGEROUS_STAGE` is set (this controller does not mark `backup` dangerous, since a partial backup is self-evidently incomplete — the underlying script's own exit code is what matters) | Re-run `backup` — it always creates a fresh, timestamped run directory, never appends to a partial one |
| `platform-deploy` | `INTERRUPTED` | Check `docker compose ps` state manually, then decide whether to re-run `platform-deploy` (idempotent — Compose reconciles to the same desired state) or `collect-diagnostics` first |
| `maintenance-on`/`off` | `INTERRUPTED` if the health-check curl itself was interrupted (rare, near-instant) | Manually confirm Loady's actual maintenance-mode state before re-running |
| `migrate` | **`INTERRUPTED`** | **Never blindly re-run.** Run `collect-diagnostics`, manually check whether the commit actually landed (via `verify-migration.sh`'s own counts) before deciding between re-running `migrate` (only if it demonstrably did not commit) or proceeding to `reconcile`/`rollback-plan` |
| `rollback` | `INTERRUPTED`, but the kill-switch layer (if it completed) already took effect | Check `state.json`'s `stages.rollback` detail for which layer completed before the interrupt, then decide whether to re-run `rollback` (kill-switch is safely repeatable) or proceed manually with the restore layer |

The one command this table treats specially is `migrate`, because it is
the single point-of-no-return action in the entire sequence
(`ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`) — an `INTERRUPTED` status
after `migrate` is a genuine "stop and look" signal, not something the
controller resolves for you by guessing.

## Locking and stale-lock recovery (Phase 28)

Every mutating command acquires an exclusive `flock` on
`.platform-production-state/<environment>/.controller.lock` before doing
anything, and releases it on exit (including on interruption, via the
`EXIT` trap). Read-only commands (`status`, `plan`, `rollback-plan`,
`collect-diagnostics`) never take the lock, so they always work even
while a mutating command is genuinely still running.

**If a command is killed hard enough that its own process is reaped
without releasing the lock** (e.g. the whole host lost power, not just an
SSH session) — `flock`'s kernel-level advisory lock is automatically
released the moment the holding process's file descriptor table is torn
down, which happens even on `SIGKILL`/power loss as soon as the OS
reclaims the process, so this is normally self-healing on the next
attempt. The one case that needs manual intervention is a **truly stuck**
holding process that is still alive but hung (not crashed) — recovery:

1. `ps aux | grep platform-production.sh` on the host to find the actual
   holding process.
2. If it is confirmed hung (not doing real work — check
   `collect-diagnostics`/`status` first), kill it directly:
   `kill -TERM <pid>` (this itself triggers the interruption handling
   above).
3. Only if the process is confirmed gone and the lock file still somehow
   blocks new invocations (should not happen with `flock`, but stated for
   completeness) — `rm .platform-production-state/<environment>/.controller.lock`
   manually, and only after confirming via `ps` that nothing is actually
   holding it.

**Never** remove the lock file while uncertain whether something is still
running — that is exactly the race Phase 28 exists to prevent.

## What recovery never does automatically

Per the mission's explicit human-gate requirement: a successful
`preflight` never auto-triggers `backup`; a successful `migration-dry-run`
never auto-triggers `migrate`; an `INTERRUPTED` status never auto-resumes
anything. Every stage transition requires its own explicit command
invocation, every time, including after a resume.
