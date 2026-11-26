# Codex Global Model Routing and Hybrid Orchestration Policy (cost-first, 1.5.0)

Updated: 2026-11-26. Apply at every session start and throughout the task. This user-level policy is in the effective `CODEX_HOME` (normally `~/.codex`) and can be superseded by a non-empty global `AGENTS.override.md`. Preserve higher-priority system/developer instructions, project guidance, security requirements, and explicit user instructions. A policy describes routing; it does not change the active model. Claim a model switch only when the runtime or spawn explicitly selected it. Canonical routing values: `~/Project/ETC/ai-agent-policy/policy/model-routing.json`; run `python3 -B -m ai_policy.routing --host codex ...` from that repo to resolve the current route.

## Objectives and routing

Token savings come first, then quality and stability. Never save tokens by skipping verification. Luna is the default; Sol is used only on escalation or for high-risk work, and Astra only as the last resort after Sol fails. Judge routes by total cost per successfully completed task, not tokens per call. Classify each task before execution and reclassify when complexity changes.

| Route | Model / effort | Use |
| --- | --- | --- |
| Main owner (root orchestrator) | Latest supported Luna family / high | Requirements, decomposition, acceptance criteria, shared interfaces, integration, final review. Directly finish small or context-coupled work when delegation costs more. |
| LEVEL 1 simple and focused research | Latest supported Luna family / medium | Renames, simple edits, docs, test writing, boilerplate, simple UI, repeating established patterns, narrow lookup, summaries, extraction. Minimal context, clear done condition, stop after verification. |
| LEVEL 2 general | Latest supported Luna family / high | Features, APIs, data logic, frontend, ordinary bugs, extensions, routine code review. |
| LEVEL 3 complex | Latest supported Luna family / xhigh | Multi-module, state management, performance, async, integration, complex data flow, architecture design. |
| LEVEL 4 critical | Latest supported Sol family / high | Major architecture change, concurrency, repeatedly unresolved errors, broad codebase analysis, security, data integrity. Scope it narrowly; prefer Sol for analysis and decisions and return implementation to Luna, unless Sol finishing directly is cheaper. Raise to xhigh only when justified. |
| LEVEL 5 last resort | Latest supported Astra family / high | Only after LEVEL 4 Sol fails twice on the same root problem. Diagnoses and fixes. Never a starting level, high-risk default, fallback, or routine reviewer. |

For Codex Luna/Sol/Astra assignments, use the canonical router's `model`. It reads the effective `CODEX_HOME/models_cache.json` and selects the highest visible, API-supported model slug matching that family when the cache is no more than 30 days old. If `model_resolution` is `pinned_fallback`, the cache could not establish the latest generation; refresh the Codex cache and rerun routing before claiming a current-generation selection. This read does not update the cache, settings, or the active root session.

Standalone Codex uses Luna as its default family. Use models and effort levels exposed by the current runtime. If a requested route is unavailable, use the configured fallback and report the substitution; if none is available, stop and preserve state. Use max only when justified; never use ultra as a default.

## Delegation and token discipline

Delegate when handoff improves the result. Establish shared contracts first and split only genuinely independent, separately verifiable tasks; keep work whole when splitting saves nothing. Default to the main owner plus one worker; at most 3 concurrent workers and at most 1 concurrent Sol/Astra worker. Give each worker a goal, ownership, interfaces, constraints, and completion criteria. Pass only directly relevant files, docs, and settings; reuse analysis already obtained; avoid duplicate agents for the same goal, repeated reads of the same files, whole-repo exploration, and nested delegation. Close finished workers and keep interim reports short. Preserve other workers' changes and avoid simultaneous edits to shared files.

The owner reviews the relevant changes, acceptance criteria, validation evidence, integration behavior, and remaining risks without repeating a worker's full investigation. A completion report includes actual verification commands and results, changes made, and remaining risks.

## Retry and escalation

For one root problem, the same executor gets at most two meaningful attempts: the first and one more based on new evidence and a materially different hypothesis. After the second failure from verification failure, unclear cause, or complexity growth, escalate one level (Luna medium → high → xhigh → Sol high → Astra high); do not escalate on failure count alone. Escalate immediately to LEVEL 4 for contradictory requirements, structural risk, or data-integrity risk. Tool, environment, permission, external-service, test-environment, and model-access failures are not model failures: keep the model, preserve state, and fix the cause. Changing models does not reset the attempt count. After two failures at LEVEL 4, escalate to the LEVEL 5 last resort (Astra); after two failures there, stop automatic escalation and give the user the evidence and the decision needed.

An escalation handoff carries only goal, related files, current implementation state, errors, attempts and results, hypotheses, and the exact decision needed, never the full transcript. After Sol resolves the problem, follow-up work returns to the task's default Luna route.

## Project policies

Preserve user-owned work. Follow project Task IDs, branch mappings, documentation, and completion gates when applicable.

## Orchestration environments

Orca-managed Runs still owned by the existing Orca follow the project's installed Orca policy and `~/Project/ETC/ai-agent-policy/docs/orca-worker-lifecycle.md`; Paseo-managed work follows the Paseo policy block (`ai-agent-policy:paseo-policy`). Each applies only when its own installed project policy and the actual task context both confirm that environment; a CLI, an environment variable or an MCP tool being present is not evidence. Outside both, this core policy applies unchanged.

## Claude Code and independent review

Use Claude Code only when installation and access are confirmed and an independent model family can materially help. Prefer the installed `claude` skill's read-only review flow. Never send secrets, credentials, `.env` content, unnecessary customer data, or unsanitized logs. Do not require external review for ordinary work.

## High-risk work and evaluation

Route destructive database work, irreversible migrations, production infrastructure, authentication/authorization, cryptography, security-critical implementation, mass data changes, and data-loss-risk schema changes through Sol high analysis and review before execution, without waiting for escalation. Cost savings never override this. Before destructive work, establish exact targets, recovery steps, and data-integrity checks.

Evaluate the policy by total tokens per successful task, first-attempt success, final correctness, elapsed time, rework, escalations, and integration defects. Use `python3 -B -m ai_policy.usage report` (log metadata only) and `... usage record` for task outcomes. Do not invent savings percentages or equate API token prices with subscription usage.
