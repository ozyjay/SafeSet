# SafeSet

A local-first CLI for minimising and pseudonymising student-allocation datasets.
**This tool can reduce disclosure risk but cannot establish that a dataset is
anonymous.** Pseudonymised information may remain re-identifiable through other
attributes or auxiliary information. Users remain responsible for deciding whether
an export is suitable for the system or service receiving it.

**Workflow:** inspect locally → apply an explicit policy → review validation →
approve export → analyse only the minimised CSV → restore authorised results locally.
The encrypted identity map stays outside the repository and export directory.
No runtime operation calls a network service. All included records are invented.

## Set up

Use the active pyenv Python 3.12+:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
python3 -m pytest
```

Dependency installation needs package access; core commands work offline. POSIX
systems are supported for private mapping storage; Windows ACLs are not implemented.

## Try the synthetic round trip

Choose private local directories outside any repository and outside cloud-synced
folders. The following creates a disposable synthetic workspace:

```bash
DEMO_DIR="$(mktemp -d)"
mkdir -m 700 "$DEMO_DIR/exports" "$DEMO_DIR/maps" "$DEMO_DIR/private"
safeset inspect examples/synthetic_students.csv
safeset sanitise examples/synthetic_students.csv \
  --policy examples/example-policy.yaml \
  --output "$DEMO_DIR/exports/safe.csv" \
  --create-map --map "$DEMO_DIR/maps/identities.enc"
safeset validate "$DEMO_DIR/exports/safe.csv" --policy examples/example-policy.yaml
# A no-change local result demonstrates restoration. Do not upload the map.
safeset restore "$DEMO_DIR/exports/safe.csv" \
  --map "$DEMO_DIR/maps/identities.enc" \
  --result-column campus --result-column subject --result-column gpa \
  --output "$DEMO_DIR/private/restored.csv" --authorise
```

Sanitise prints a summary and asks for export approval, then a hidden passphrase
(minimum 16 characters, confirmed). `--approve-export` explicitly approves the
reviewed operation for scripted use but does not bypass validation or the secret
prompt. `--create-map` is always required; omitting `--map` chooses a random filename
under `~/.local/share/safeset/maps/`. No secret argument/environment option exists.
Retain your passphrase securely and separately; there is no recovery backdoor.

Restore prompts to unlock the map. It restores **only the selected source key**,
not dropped names or notes. All mapped records must occur exactly once; returned
non-ID fields require repeated `--result-column` allowlisting. Restored output is
sensitive plaintext. The CLI never overwrites files, and operational outputs are
rejected inside detected repositories. Exit 0 means success; rejected inputs,
validation failure or missing authorisation return a non-zero exit status.

## Scope and development

MVP actions: drop, categorical keep, numeric bin and random pseudonymisation.
CSV and YAML have strict schemas and resource limits. Passing group-size checks
is not evidence of anonymity. This foundation has no independent security audit.
See [architecture](docs/architecture.md), [threat model](docs/threat-model.md),
[safety model](docs/data-safety-model.md), [policy format](docs/policy-format.md),
[implementation plan](docs/development-plan.md) and [verification](docs/verification.md).

Run `python3 -m pytest`, `ruff check .`, `ruff format --check .` and
`python3 -m build` before release. `AGENTS.md` and `.github/skills/` support ongoing
Codex and compatible VS Code agent work. Never put real source data into this
checkout, issue reports, agent conversations or test fixtures.
