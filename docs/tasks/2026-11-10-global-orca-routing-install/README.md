# Global Orca routing policy install

TASK_ID: `2026-11-10-global-orca-routing-install`

## Purpose

Apply the approved lightweight Orca Main/Controller routing policy to the actual Codex and Claude global instruction files and align both installed Orca orchestration skill copies with the approved conditional Controller rule, preserving unrelated instructions and file permissions.

## Source and approval

- Source of policy wording: the reviewed, locally modified files in the ai-agent-policy main checkout: `codex-global-model-routing-prompt.md` and `claude-code-global-model-routing-prompt.md`.
- The source checkout's unrelated pre-existing modifications and `.local-artifacts/` are preserved and are read-only inputs for this task.
- User explicitly approved creating the required integration/task worktrees and applying the approved policy to the actual usage environment on 2026-11-10.

## Scope

- Update only the Orca-related managed block in the user's Codex global instructions and the corresponding Orca section in Claude global instructions.
- Create private backups before mutation; preserve unrelated file contents, ownership and modes.
- Verify the intended policy text, managed-block boundaries, and preservation of all out-of-scope content after installation.
- Do not change model-routing rules outside the requested Orca coordinator simplification, hooks, agents, credentials, settings, project source, or GH project policy.
- GH project policy is a separate project and requires its own Task/worktree and installation procedure; it is not part of this task.

## Acceptance criteria

1. Both actual global files and both installed Orca skill copies contain the approved policy text.
2. Only the relevant managed policy sections change; unrelated instructions remain byte-identical.
3. Backups preserve the original bytes and modes, and both installed files retain their original modes and ownership.
4. Static checks confirm no duplicate or malformed managed markers and verify the installed policy text against its source.
5. Record exact changed paths, private backup locations in local evidence only, verification commands/results, and runtime-loading/upstream-source limitations.

## Repository and worktree mapping

| Repository | Branch | Base | Role |
|---|---|---|---|
| `wody-hub/ai-agent-policy` | `feature/2026-11-10-global-orca-routing-install` | `dev` at `7936f0138660511f29a8d75e55f12c1252db59db` | Task record and installation evidence |

The task branch is an Orca-managed direct child of the verified `dev` worktree. The global files are machine-level targets outside Git; their absolute paths and private backup details are recorded only in local execution evidence, not shared repository records.

## Completion record

- Status: global instructions and installed skill copies updated and statically verified on 2026-11-10; runtime loading not verified.
- Approved scope extension: in addition to the two global instruction files, update both installed `orca-orchestrator/SKILL.md` copies to align with the approved policy. Detailed wording and machine-local target paths are recorded only in private execution evidence.
- Global instruction changes and prior validation: see the preceding installation record in local execution evidence; the existing global files were not modified during this skill alignment task.
- Skill changes: approved alignment updates were applied to both installed skill copies, including the approved mail-ownership clarification. Both installed skill files are byte-identical after the edits; detailed hashes and metadata are recorded only in private execution evidence.
- Validation (no tests run): exact before/after review confirms only the two intended bullets changed; both copies compare equal and have the same SHA-256; private backups compare byte-for-byte with the original files and retain mode 644. Global-file checks remain as documented in private execution evidence. Historical `.bak-20261106-cost-routing` files were not modified.
- Private backup paths and detailed validation evidence are recorded only in `.local-artifacts/tasks/2026-11-10-global-orca-routing-install/` and are not committed.
- Source limitation: the installed skill has no tracked upstream source in this repository or `~/.agents/skills`; changes apply to the two installed copies only.
- Runtime limitation: no app/session or runtime hook was launched. Runtime loading remains unverified; a new session may be required to load the updated skill and global instruction files.
- Tests: not run, as requested. No servers or background processes were started.
- Push, merge, and deployment: not performed.

### Approved mail-ownership clarification — 2026-11-10

- The user approved and both installed skill copies received a minimal mail-ownership clarification. This resolved the earlier skill conflict recorded in private execution evidence. Exact target details and validation remain private.
