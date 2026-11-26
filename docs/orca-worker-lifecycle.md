> **Archived (parallel period, 2026-11-25).** The coordination tool moves from Orca to Paseo. Use this document only to finish Runs and worktrees that Orca already owns during the parallel period; new Tasks follow [Paseo policy](paseo-agent-lifecycle.md). It is not deleted; it becomes archived once every Orca Run is settled and its Dispatch is released (see [migration design](paseo-migration-design.md), Q1).

# Orca managed Worker lifecycle

This rulebook applies to Orca-supervised managed Workers. Project Task registration, Gitflow/worktree rules, Human Gates, and user authorization remain governed by their existing policies. It does not imply that direct terminal/agent sessions or Codex/Claude child agents are Orca-managed or automatically stopped.

## Run ownership and completion delivery

- Assign exactly one Main or Controller as owner of each Run. That owner passes the same `--run <run_id>` to `worker-start`, `task`, and every `check`; it handles only messages for its Run. If a separate Controller owns the Run, the Main routes its wake/message to that Controller; the Run owner handles its own messages.
- Prefer runtime wake-based delivery when available. Where a wake is unavailable, unreliable, or not delivered to the Run owner, use bounded blocking waits: `orca orchestration check --run <run_id> --wait --timeout-ms <limit>`. On timeout, inspect only that Run and either make another bounded wait or report its current state. A timeout does not mean completion or failure.
- Never use an unscoped `check` or plain/repeated polling to wait for completion. Do not wait for automatic session cleanup as a substitute for handling the result.

## Controller resume and handoff

1. A Run ID selects the Run and does not bind a new Controller. On `consumer_fenced`, stop consuming mail and making changes. Use supported `run-show --id <run_id>` and `inbox --terminal run:<run_id>` reads to reconcile the host, latest results and unresolved Dispatches. Even `check --peek` can require the current binding.
2. For a planned handoff, the current Controller stops waits, reads and dispatches, then transfers handled results, outstanding work and any uncertain mutation receipts. If it is unavailable, reconcile those items from the durable records and mark any gaps before proceeding. Do not repeat work whose outcome is uncertain.
3. In an eligible Controller session at the Run's home Orca, preferably one with no other Run bindings, execute `orca orchestration run-use --id <run_id>`. This changes the binding and may unbind other Runs held by that session. Verify the intended binding with `orca orchestration run-current` and reconcile the existing Tasks, Dispatches and unread mail before starting or releasing any Worker. Only the newly bound Controller resumes consumption. If the binding outcome is unknown, inspect it or recover the exact request using its receipt; do not start a replacement Run to bypass the fence.
4. Worker placement can span hosts. Controller binding remains at the Run's home; a peer Run cannot be taken over from the other host. A Worker cannot take over its own or an ancestor Run. Use `--takeover-legacy` only for an eligible automatically adopted legacy Run under the runtime's documented recovery procedure.

## Worktree readiness before dispatch

For a newly created managed worktree in a project that requires local policy,
creation includes a separate policy-setup step before ordinary Worker dispatch.
The project owner maintains a versioned, reviewed installation manifest naming
the policy entrypoints, policy snapshot and manifest, guard, and applicable
client adapters. On the target execution host, use the project's supported
installer or, when permitted by the project, have the responsible AI copy the
explicitly listed files from the verified source without overwriting existing
files. Do not assume Git worktree creation copied ignored files. Verify copied
bytes and modes against the source and manifest. Record the actual source version, file
hashes, target worktree and installation result. Setup must preserve pre-existing
files and user changes, refuse unexpected differences rather than overwrite
them, and provide a documented recovery or rollback path. Do not copy secrets,
private Task contexts, credentials, or unrelated configuration from a parent.

Treat worktree creation, policy file installation, client trust and actual hook
loading as distinct states. Report ready only after the readiness checks below
pass. If no supported installer or project-permitted direct copy is available,
retain the worktree, report policy setup pending, and use the project's
authorized installation or recovery path before dispatch.
Do not silently replace or bypass a project's stricter setup requirements.

1. When a project requires local policy installation, the Run owner checks the exact target worktree on its execution host before assigning or resuming an ordinary Worker. Verify the actual repository, branch, creation base, required parent and Task mapping against project policy. Use the project's approved install manifest or equivalent to verify the required entry instructions, policy files, guard and selected client's hook configuration. Record separately whether the files are valid and whether required hooks are trusted and load in the intended execution path. A checkout, `setup=run` request or setup receipt alone does not establish policy readiness. Projects without such an installation requirement follow their existing start checks.
2. If required files are missing, record “policy installation required”. If the setup, installed bytes or hook loading cannot be verified, record the specific blocker and stop ordinary dispatch. Preserve the current Task, worktree and changes. Record the cause and follow the project's authorized install or recovery path on the existing worktree if eligible. If that path is unavailable or unauthorized, report the blocker. Do not regenerate the worktree, switch clients, or retry the same launch to avoid the check. Recheck when installation, configuration or other evidence relevant to the blocker changes.
3. Before ordinary work resumes, verify the installed version and manifest, confirm policy and hook loading in a fresh session for the selected client, and verify the required allowed and denied cases through the project's supported checks. Deliver the ordinary work prompt only after these checks pass. When Orca cannot wait for setup, separate worktree creation and Worker assignment. Only a project's authorized installation or recovery task may proceed under its limited setup exception.

## Settlement and release

- Preserve the Worker result and verification evidence, then confirm the exact Dispatch is settled (`worker_done` or a settled failure) before cleanup.
- Immediately after settlement and result capture, run `orca orchestration worker-release --dispatch <dispatch_id>` for that exact Dispatch and record `released`, `release_pending`, or `release_unknown`. A settled failure is also released after its result is captured.
- Do not release an active, uncertain, unsettled, user-owned, pre-existing, or unverified session. Follow the established stop/recovery path when settlement or ownership is unclear. Do not infer that a timeout, closed terminal, or automatic retention means the process stopped.
- Keep a settled Worker open only when the user explicitly asks to keep that session, and record the reason and intended holder. New child/top-level worktree Workers may remain open by default; release them unless that explicit request applies.
- Do not claim direct terminal/agent or Codex/Claude child-agent shutdown or release unless the runtime provides evidence for that exact session. Report lifecycle as unverified when it cannot be established.

Completion reports include the Dispatch outcome, release state, preserved result/verification, and any unresolved lifecycle status.

## Worker result and Task handoff

- Each Worker sends one concise result with the Task ID, Dispatch ID, outcome, changed files and summary, verification commands and results with evidence references, unverified items or blockers, and the next action. Include release state in the Run owner's record after settlement and release. Record unknown values as unverified.
- The Run owner uses this result for integration and follows its references when more detail is needed. Preserve the source evidence. Include applicable acceptance criteria and constraints in handoffs for high-risk independent review. A settled Dispatch records Worker execution status. The project Task policy governs overall completion and any required production verification.
- When available, record requested and confirmed tool/model/effort, elapsed time, retry count and cause, and verification status alongside the Task and Dispatch IDs. Use the existing usage recorder for supported outcome fields under the same Task ID and keep Dispatch-specific details in the result. Leave unavailable measurements blank. Compare tokens, elapsed time and rework per verified Task, accounting for all attempts where measurements can be linked.
