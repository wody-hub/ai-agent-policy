# Global Orca routing policy install

TASK_ID: `2026-11-10-global-orca-routing-install`

## Purpose

Apply the approved lightweight Orca Main/Controller routing policy to the actual Codex and Claude global instruction files while preserving all unrelated instructions and existing file permissions.

## Source and approval

- Source of policy wording: the reviewed, locally modified files in the ai-agent-policy main checkout: `codex-global-model-routing-prompt.md` and `claude-code-global-model-routing-prompt.md`.
- The source checkout's unrelated pre-existing modifications and `.local-artifacts/` are preserved and are read-only inputs for this task.
- User explicitly approved creating the required integration/task worktrees and applying the approved policy to the actual usage environment on 2026-11-10.

## Scope

- Update only the Orca-related managed block in the user's Codex global instructions and the corresponding Orca section in Claude global instructions.
- Create private backups before mutation; preserve unrelated file contents, ownership and modes.
- Verify the intended policy text, managed-block boundaries, and preservation of all out-of-scope content after installation.
- Do not change model-routing rules outside the requested Orca coordinator simplification, hooks, agents, credentials, settings, project source, or GH project policy.
- GH project policy is a separate project and requires its own Controller, Task, dev child worktree, and installation procedure; it is not part of this task.

## Acceptance criteria

1. Both actual global files contain the approved rule: Main may act as Controller for one short, low-risk project goal with one Worker; use a separate Controller for multi-project, parallel, long-running, high-risk, or complex coordination; managed Workers perform actual work.
2. Only the relevant managed policy sections change; unrelated instructions remain byte-identical.
3. Backups preserve the original bytes and modes, and both installed files retain their original modes and ownership.
4. Static checks confirm no duplicate or malformed managed markers and verify the installed policy text against its source.
5. Report exact paths, backup locations, verification commands/results, and any unsupported runtime-loading behavior.

## Repository and worktree mapping

| Repository | Branch | Base | Role |
|---|---|---|---|
| `wody-hub/ai-agent-policy` | `feature/2026-11-10-global-orca-routing-install` | `dev` at `7936f0138660511f29a8d75e55f12c1252db59db` | Task record and installation evidence |

The task branch is an Orca-managed direct child of the verified `dev` worktree. The global files are machine-level targets outside Git; their absolute paths and private backup details are recorded only in local execution evidence, not shared repository records.

## Completion record

- Status: installed and statically verified on 2026-11-10 by the Orca Worker.
- Change: in each global file, the managed block's Orca paragraph had one span (the fixed "Main → per-project Controller → Workers" structure, Controller-owned Run, and mail forwarding) replaced in place. The new text renders the approved source bullet (`codex-global-model-routing-prompt.md` line 66, `claude-code-global-model-routing-prompt.md` line 77) in the block's existing concise English style. It keeps the existing `orca-orchestrator`, Controller model, and `check --wait` details. The retry sentence and every other byte are unchanged.
- Wording is a rendering, not a verbatim copy: the source prompts contain only the Korean rule and tell the installer to reflect it concisely in English. Each clause maps to the source: conditional Main-as-Controller, Workers do the actual work, separate Controller criteria, one Run owner with `--run`, and message routing by owner.
- Validation (no tests run, as instructed):
  - Exact-match check before writing: old span ×1, new span ×0, no CR bytes in either file.
  - After writing: the bytes before and after the replaced span are identical to the backup, and reversing the substitution reproduces the backup exactly. `diff` shows one changed line per file.
  - Managed start/end markers: one of each per file; the new text sits inside the managed block.
  - Mode, owner, inode, link count, xattrs, LF line endings, and the trailing newline are unchanged (Codex 644, Claude 600).
  - Backups are byte-identical (`cmp`) with matching sha256 and preserved modes. They are stored privately in the local task-artifact area; paths and hashes are in local execution evidence only.
- Shadowing: no Codex override file, no Claude local global file, and no config-dir environment overrides were found.
- Remaining limits:
  - The installed `orca-orchestrator` skill (both Claude and Codex copies, line 23) still says every Project·Goal goes to a separate Controller. That conflicts with the new rule. Skills were out of scope, so it needs a separate approved change.
  - The managed-block header dates were not changed.
  - Runtime loading was not verified: no new model session was started. Existing sessions keep the old text until a new session loads the files (`/context` in Claude Code; a new Codex session).
- Local Task-document commit: Task docs only; global files and private evidence are not committed.
- Push, merge, and deployment: not authorized by this task.
