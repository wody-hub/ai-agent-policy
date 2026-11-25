# Reproducible Paseo policy bundle

Status: draft (2026-11-25). Companion to [Reproducible Orca policy bundle](reproducible-orca-environment.md), which is archived for the parallel period but whose installer rules apply unchanged.

The same standard-library CLI (`python3 -B -m ai_policy`) installs a second bundle flavor, `paseo`, from `policy/paseo-bundle.json`. A manifest without a `flavor` key is an Orca manifest; `"flavor": "paseo"` selects the Paseo file set (`policy/paseo-common.md`, `policy/adapters/paseo-claude.md`, `policy/adapters/paseo-codex.md` and the same five `ai_policy` modules). Every command takes `--flavor orca|paseo` (default `orca`), and a bundle of the other flavor is refused (`bundle_flavor_mismatch`).

| | Orca | Paseo |
|---|---|---|
| Manifest | `policy/bundle.json` | `policy/paseo-bundle.json` |
| Install root (under the explicit home) | `.config/ai-agent-policy/orca` | `.config/ai-agent-policy/paseo` |
| Adapter markers in `.codex/AGENTS.md`, `.claude/CLAUDE.md` | `ai-agent-policy:orca-adapter:` | `ai-agent-policy:paseo-adapter:` |
| Common body | `policy/orca-common.md` | `policy/paseo-common.md` |

Both flavors can be installed into one home; each has its own state, journal, backups and markers, and removing or restoring one leaves the other's block untouched.

## Rules that carry over

- Explicit `--home` only; there is no default home. `install`, `remove` and `restore` need `--dry-run` (prints the plan and its `plan_sha256`) or `--plan-sha256 <digest>` of an unchanged plan. Tests use temporary directories only.
- The installer never writes global files outside the explicit home, never fetches remotely and installs no hook.
- File validity does not prove session load, origin or enforcement.

## Paseo context evidence

`ai_policy.context.decide_paseo` returns `active` only when both the parent's assignment message and the agent's own parent label `paseo.parent-agent-id` are attested, the workspace does not mismatch, and the installed bundle verifies. The `PASEO_AGENT_ID` environment variable is a hint and never evidence by itself (hint only → `ambiguous`, `origin_unverified`). A subprocess cannot read the assignment message or the label, so `detect`/`context --flavor paseo` cannot become active; a host integration that reads the agent's runtime record would build `PaseoEvidence` and call `decide_paseo`. No such integration exists yet.

## Building the manifests

`python3 -B scripts/build_bundles.py --source-commit <sha>` rewrites both manifests from the working tree (file hashes, the five provenance hashes, source commit). Provenance fields are inputs, not proof of publisher identity.
