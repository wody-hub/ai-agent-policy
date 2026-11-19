# Orca managed Worker lifecycle

This rulebook applies to Orca-supervised managed Workers. Project Task registration, Gitflow/worktree rules, Human Gates, and user authorization remain governed by their existing policies. It does not imply that direct terminal/agent sessions or Codex/Claude child agents are Orca-managed or automatically stopped.

## Run ownership and completion delivery

- Assign exactly one Main or Controller as owner of each Run. That owner passes the same `--run <run_id>` to `worker-start`, `task`, and every `check`; it handles only messages for its Run. If a separate Controller owns the Run, the Main routes its wake/message to that Controller; the Run owner handles its own messages.
- Prefer runtime wake-based delivery when available. Where a wake is unavailable, unreliable, or not delivered to the Run owner, use bounded blocking waits: `orca orchestration check --run <run_id> --wait --timeout-ms <limit>`. On timeout, inspect only that Run and either make another bounded wait or report its current state. A timeout does not mean completion or failure.
- Never use an unscoped `check` or plain/repeated polling to wait for completion. Do not wait for automatic session cleanup as a substitute for handling the result.

## Settlement and release

- Preserve the Worker result and verification evidence, then confirm the exact Dispatch is settled (`worker_done` or a settled failure) before cleanup.
- Immediately after settlement and result capture, run `orca orchestration worker-release --dispatch <dispatch_id>` for that exact Dispatch and record `released`, `release_pending`, or `release_unknown`. A settled failure is also released after its result is captured.
- Do not release an active, uncertain, unsettled, user-owned, pre-existing, or unverified session. Follow the established stop/recovery path when settlement or ownership is unclear. Do not infer that a timeout, closed terminal, or automatic retention means the process stopped.
- Keep a settled Worker open only when the user explicitly asks to keep that session, and record the reason and intended holder. New child/top-level worktree Workers may remain open by default; release them unless that explicit request applies.
- Do not claim direct terminal/agent or Codex/Claude child-agent shutdown or release unless the runtime provides evidence for that exact session. Report lifecycle as unverified when it cannot be established.

Completion reports include the Dispatch outcome, release state, preserved result/verification, and any unresolved lifecycle status.
