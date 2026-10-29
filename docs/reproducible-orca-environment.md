# Reproducible Orca policy bundle

This repository provides a Python standard-library CLI for a shared Orca policy
bundle, conditional Codex/Claude adapters, and explicit-home installation,
inspection, removal and restoration. Repository tests and synthetic-home
installation are validated; live automatic loading and full AI environment
restoration remain pending.

The new G1 candidate consists of the [bundle manifest](../policy/bundle.json),
[shared body](../policy/orca-common.md) and conditional
[Codex](../policy/adapters/codex.md)/[Claude](../policy/adapters/claude.md) adapters.
Original policy sources remain the [repository overview](../README.md),
[Codex routing](../codex-global-model-routing-prompt.md),
[Claude routing](../claude-code-global-model-routing-prompt.md),
[Orca project setup](../orca-project-setup.md) and
[project Task setup](../project-task-policy-setup.md).
These original sources are unchanged. G1 candidate acceptance covers repository
code and temporary-home fixtures; effective installed policy and any source
reconciliation require their own review and live-loading evidence.

Run from the repository root with Python 3.10 or later. No dependency installation
is required:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v
python3 -B -m ai_policy detect --mode auto --format json
python3 -B -m ai_policy context --mode auto --format text
```

`detect` returns structured evidence. `context` emits policy bytes only after
verified activation and otherwise emits no policy. Exit codes are 0 for success
or active, 10 for absent or inactive, 20 for ambiguous or unsupported, 30 for
installation, integrity or filesystem errors, and 2 for invalid CLI arguments.

After an explicit user request for Orca guidance, the guidance command is:

```sh
python3 -B -m ai_policy guide --explicit-request --bundle policy/bundle.json
```

The flag records a chosen guidance mode; it cannot establish consent or prove
that the invocation originated in a managed terminal.

## Try an isolated installation

This example writes only into a newly created temporary home. It leaves the
process HOME unchanged and does not install live hooks or change real settings.
Each mutation uses the digest from its immediately preceding dry-run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B - <<'PY'
import json
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path.cwd().resolve()

def invoke(*args, entry=None, expected=0):
    command = [str(entry)] if entry else [sys.executable, '-B', '-m', 'ai_policy']
    result = subprocess.run([*command, *map(str, args)], cwd=repo,
                            capture_output=True, timeout=30)
    assert result.returncode == expected, (args[0], result.returncode)
    return json.loads(result.stdout)

with tempfile.TemporaryDirectory(prefix='ai-policy-example-') as temporary:
    home = Path(temporary).resolve()
    args = ('install', '--home', home, '--bundle', repo / 'policy/bundle.json')
    plan = invoke(*args, '--dry-run')
    installed = invoke(*args, '--plan-sha256', plan['plan_sha256'])
    entry = home / '.config/ai-agent-policy/orca/entrypoint.py'
    checked = invoke('check', '--home', home, entry=entry)
    assert checked['files_valid'] and checked['ownership_valid']
    assert checked['load_verified'] is None and checked['origin_verified'] is None

    args = ('remove', '--home', home)
    plan = invoke(*args, '--dry-run', entry=entry)
    removed = invoke(*args, '--plan-sha256', plan['plan_sha256'], entry=entry)
    assert invoke('check', '--home', home, entry=entry, expected=10)['state'] == 'absent'

    args = ('restore', '--home', home, '--backup', removed['backup_id'])
    plan = invoke(*args, '--dry-run', entry=entry)
    invoke(*args, '--plan-sha256', plan['plan_sha256'], entry=entry)
    assert invoke('check', '--home', home, entry=entry)['files_valid']
    print('PASS temporary-home install/check/remove/restore')
PY
```

The [source-independent regression](../tests/test_install.py) additionally
installs from a temporary source copy, deletes only that copy, then exercises
the retained installed entrypoint under hostile cwd, PYTHONPATH and PATH values.
It verifies remove, absent check, restore, installed check and no generation
bytecode. This proves offline restoration in that fixture, not live loading.

## Ownership, backup and recovery

Install requires explicit absolute `--home` and `--bundle`. Remove and restore
also require explicit absolute `--home`; restore requires `--backup`. Dry-run
renders in memory without creating files, directories, locks or backups. Its
digest binds the bundle, home, target bytes, modes, existence and intended changes.
Changed inputs or stale digests refuse application. Reinstalling the same intact
bundle is a no-op, including timestamps and backups.

The component root is `<home>/.config/ai-agent-policy/orca`. Managed blocks keep
ownership separate from personal entrypoint text. Private backups contain exact
preimages/postimages, modes, existence records and checksums. Restoring the first
installation backup returns original entrypoint bytes, modes and existence while
preserving compatible later personal text. Drift, malformed markers, corrupted
backups, unsafe paths and conflicting personal modes refuse before target writes.

`remove` disables active adapters and selectors while retaining `entrypoint.py`,
`runtime.json`, immutable generations and backups. The retained runtime does not
activate policy and allows offline restoration after source removal. Reverting
the first installation can remove originally absent installer files too; keep a
reviewed offline source/bundle for any later work from that fully reverted state.

Application uses an exclusive writer, write-ahead journal, native atomic
exchange/no-clobber operations and fsync; the active selector changes last.
Rollback requires successful kernel-transition receipts and retained/published
inode ownership. Concurrent external edits are preserved, with actual displaced
versions retained for inspection. There is no multi-file atomicity guarantee.
Darwin native operations were tested; Linux support is implemented but has not
been live-tested here. Unsupported native operations or cross-device targets
refuse without a lossy fallback.

Interrupted journals or uncertain cleanup leave `recovery_required`, suppressing
policy output and blocking further mutation. Startup never resumes a transaction,
removes stale locks or prunes retained versions. An operator must inspect the
private journal, backup and retained-slot metadata and approve a recovery plan.
Backups and retained versions are not automatically deleted. Local hashes prove
integrity relative to the reviewed bundle; they are not publisher signatures.

## Live activation and remaining gates

Real automatic detection currently returns `ambiguous/executable_unsupported`
with `policy_emitted=false` on the validated Mac environment. The fixed Orca
executable's parent safety check refuses a group-writable application directory.
No trust override or permission change is provided. Matching terminal/workspace
metadata alone also cannot prove invocation origin, even with a trusted executable.

The installed entrypoint verifies pinned source bytes before source-only imports
and ignores unchecked bytecode caches. This integrity check does not establish
the caller's origin. File and block ownership checks are separate from hooks,
actual loading and enforcement: no native hooks are installed by this component,
and load/origin/enforcement remain unverified.

Before live use, establish a supported invocation-binding contract, validate native
startup events and loading exactly once, test ordinary managed and external/VSCode
sessions before any Run/Task and across restarts, review generated targets and
recovery, and obtain separate live-install approval. Full configured model, agent,
skill and project-adapter inventory/restoration is a later stage; credentials are
excluded. Existing canonical policy documents and source reconciliation remain
separate review gates.
