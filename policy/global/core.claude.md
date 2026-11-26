# Claude Code model routing policy (cost-first, 1.5.0, 2026-11-26)

This is the user's global model operating policy. Follow system, developer, organization, and applicable project instructions first. A role name or configured model is not proof of the model that actually ran; report the model and effort only from runtime evidence. The canonical routing values live in `~/Project/ETC/ai-agent-policy/policy/model-routing.json`; `python3 -B -m ai_policy.routing` (run from that repo) returns the route for a task.

## Default models and complexity levels

Token savings come first, then quality and stability. Never save tokens by skipping verification. Sonnet is the default; Opus is not a default executor and is used only on escalation or for high-risk work. Classify each task before execution and reclassify if complexity changes.

| Route | Model / effort | Use |
| --- | --- | --- |
| Main session (root orchestrator) | Sonnet 5.5 medium | Requirements, decomposition, acceptance criteria, shared contracts, integration, final review. Finish short or context-bound work directly when delegation costs more. |
| LEVEL 1 simple (`sonnet-light`) | Sonnet 5.5 low | Renames, simple edits, docs, test writing, boilerplate, simple UI, repeating existing patterns, ordinary code reading. Minimal context, clear done condition, stop after verification. |
| LEVEL 2 general (`sonnet-engineer`) | Sonnet 5.5 medium | Features, APIs, data logic, frontend, ordinary bugs, extensions, ordinary code review. |
| LEVEL 3 complex (`sonnet-debugger`) | Sonnet 5.5 high | Multi-module, state management, performance, async, integration, complex data flow, architecture design, reproducible bugs with demanding verification. |
| Lookup (`haiku-worker`) | Haiku 4.5 | Bounded file/symbol lookup, extraction, short summaries only. No design, security, or difficult debugging. |
| LEVEL 4 critical (`opus-lead` advice, `opus-specialist` implementation) | Opus 5.5 high | Major architecture change, concurrency, repeatedly unresolved errors, broad codebase analysis, security, data integrity. Scope it narrowly; prefer analysis/decisions by Opus and implementation back on Sonnet. Opus may implement directly when that is cheaper. |
| LEVEL 5 last resort (`fable-specialist`) | Fable 5.1 high | Only after LEVEL 4 Opus fails twice on the same root problem. Diagnoses and fixes. Never a starting level, high-risk default, or fallback. Access verified 2026-11-06. |

Do not call Codex just to reach Luna; cross-tool transfer costs more than it saves. Use Codex only for independent review when another model family materially improves an important decision; confirm its actual model first and send only a sanitized diff and evidence.

## Escalation, attempts, and handoffs

For the same root problem, allow an initial implementation and at most one evidence-based repair using a materially different hypothesis. After the second failure from verification failure, unclear cause, or complexity growth, escalate one level (Sonnet low → medium → high → Opus high → Fable high); do not escalate on failure count alone. Escalate immediately to LEVEL 4 for contradictory requirements, structural risk, or data-integrity risk. Tool, permission, environment, external-service, test-environment, and model-access failures are not model failures: keep the model, preserve state, and fix the cause. A model change does not reset the attempt count. After two failures at LEVEL 4, escalate to the LEVEL 5 last resort (Fable); after two failures there, stop automatic escalation and give the user the evidence and the decision needed.

An escalation handoff carries only: goal, related files, current implementation state, errors, attempts and results, hypotheses, and the exact decision needed — never the full transcript. After the premium model resolves the problem, follow-up work returns to the task's default level model.

A normal assignment states the goal, relevant context, owned files or responsibility, interfaces, constraints, and done conditions. Preserve other workers' edits. The lead checks the relevant diff, acceptance criteria, actual validation evidence, and integrated behavior without repeating investigations that the handoff already supports.

## Token discipline

Pass only files, docs, and settings directly relevant to the task; reuse analysis already obtained; avoid repeated reads of the same files and whole-repo exploration. Split work only into independently verifiable units and keep it whole when splitting saves nothing. Default to main plus one worker; use at most 3 concurrent workers and at most 1 concurrent Opus/Fable worker combined, only for independent tasks with disjoint ownership. Do not create duplicate agents for the same goal, close finished agents, and keep interim reports short. Evaluate routing by total tokens per successful task, not tokens per call: `python3 -B -m ai_policy.usage report` and `... usage record` in the policy repo.

## Project policies

Preserve user-owned work. Follow project Task IDs, branch mappings, documentation, and completion gates when applicable.

## Orchestration environments

Orca-managed Runs still owned by the existing Orca follow the project's installed Orca policy and `~/Project/ETC/ai-agent-policy/docs/orca-worker-lifecycle.md`; Paseo-managed work follows the Paseo policy block (`ai-agent-policy:paseo-policy`). Each applies only when its own installed project policy and the actual task context both confirm that environment; a CLI, an environment variable or an MCP tool being present is not evidence. Outside both, this core policy applies unchanged.

## Safety and project workflow

Authentication/authorization, cryptography, production infrastructure, destructive database work, and migrations with data-loss risk require Opus high analysis and review before execution, without waiting for escalation. Cost savings never override this. Confirm exact targets, recovery, and data-integrity checks before any destructive action. Do not broaden tool or permission access to make a model route work. Follow an installed project Task policy when applicable. Keep personal drafts and raw evidence in the local task-artifact area; put only reviewed team documents in the shared task-docs location, as required by the project policy.

At completion, report changed files, actual verification commands/results, integration evidence, and remaining risks or unknowns. File presence, JSON parsing, or an agent's success message alone does not establish runtime model/effort application. In a new ordinary session, check `/context`, `/model`, `/effort`, and `/tasks` as applicable. Existing sessions, safe mode, and bare mode can load different instructions or settings.

## Runtime notes

`~/.claude/settings.json` selects `claude-sonnet-5-5` and stores per-model effort: Sonnet 5.5 medium, Opus 5.5 high. `sonnet-light` (low), `sonnet-engineer` (medium), `sonnet-debugger` (high), and `opus-lead`/`opus-specialist` (high) request their own effort in agent frontmatter. Organization policy, project settings, CLI flags, `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`, and `CLAUDE_CODE_EFFORT_LEVEL` can override these defaults. The existing `ANTHROPIC_BASE_URL` proxy setting is preserved and may affect normal sessions. Verify effective settings in a new regular session; do not infer them from this file.
