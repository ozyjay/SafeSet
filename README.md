# SafeSet

A local-first desktop interface and CLI for minimising and pseudonymising
student-allocation datasets.
**This tool can reduce disclosure risk but cannot establish that a dataset is
anonymous.** Pseudonymised information may remain re-identifiable through other
attributes or auxiliary information. Users remain responsible for deciding whether
an export is suitable for the system or service receiving it.

**Workflow:** inspect locally → apply an explicit policy → review validation →
approve export → analyse only the minimised Excel workbook → restore authorised results locally.
The encrypted identity map stays outside the repository and export directory.
No runtime operation calls a network service. All included records are invented.
The version 2 example replaces campus and subject values with fresh random codes
per export, while retaining GPA exactly within a declared 0–7 range and two decimal
places. Exact GPA can still disclose information; passing validation is not a
decision to share the Excel workbook with any particular service.

## Set up

In `pwsh`, use the active pyenv Python 3.12+:

```pwsh
python3 -m venv .venv
./.venv/bin/Activate.ps1
python3 -m pip install -e '.[dev]'
python3 -m pytest
```

Dependency installation needs package access; core commands work offline. POSIX
systems are supported for private mapping storage; Windows ACLs are not implemented.

## Try the synthetic round trip

For a guided local interface, run `safeset desktop` after installation (or
`safeset-desktop` after reinstalling this version). **Inspect** shows aggregate
characteristics only. Select one or more worksheets after choosing a workbook with several
visible sheets; SafeSet combines their rows for inspection, policy authoring and
export. From there, use an existing policy or open **Policy** to
create a version 2 policy from the Excel workbook headings. Choose an action and classification
for every column, set its allowed categories or numeric limits, and choose a
minimum group size. Category values are shown only if you explicitly request them
locally in a field's settings. You can also load an existing policy's choices and
save a revised policy under a new filename. Save policies outside repositories;
it is then selected in **Export**. The policy may contain sensitive category labels.

In **Export**,
choose a policy and a *new* export filename outside a repository. Leave the map
destination empty for a random filename in SafeSet's private map directory, or
choose a separate private directory. **Prepare review** shows the validation
findings, policy decisions and both destinations. A failed check blocks export.
After approval, both saved paths stay visible and the map path carries into Restore.

In **Restore**, choose the analysed Excel workbook and click **Read result columns**. SafeSet
shows only its row count and headings; approve every returned non-ID column you
intend to restore. If a returned column is not wanted, remove it from the analysed
Excel workbook locally and read the file again. Then choose the encrypted map and a *new*
restored Excel workbook filename. SafeSet checks those paths before asking for the map
passphrase and separate restoration authorisation.
The desktop interface uses Tk locally; it opens no server or network connection.
The CLI remains available for scripts and terminals.
For a workbook with several visible sheets, repeat `--sheet 'Worksheet name'` on
`inspect`, `sanitise`, `validate` or `restore` to combine sheets. Their headings
must match in the same order. Duplicate participant keys block export; filter the
updated sheet to new participants before combining overlapping cohorts.
Structured Excel Tables are supported. SafeSet reads their defined ranges and
ignores titles or notes outside them; matching tables on a selected sheet are combined.
For a step-by-step desktop and CLI guide, see [HOWTO.md](HOWTO.md).

Choose private local directories outside any repository and outside cloud-synced
folders. The following creates a disposable synthetic workspace:

```pwsh
$DemoDir = (mktemp -d).Trim()
$Exports = Join-Path $DemoDir 'exports'
$Maps = Join-Path $DemoDir 'maps'
$Private = Join-Path $DemoDir 'private'
New-Item -ItemType Directory -Path $Exports, $Maps, $Private | Out-Null
chmod 700 $DemoDir $Exports $Maps $Private
$ExportExcel = Join-Path $Exports 'safe.xlsx'
$MapFile = Join-Path $Maps 'identities.enc'
$RestoredExcel = Join-Path $Private 'restored.xlsx'
safeset inspect examples/synthetic_students.xlsx
safeset sanitise examples/synthetic_students.xlsx --policy examples/example-policy.yaml --output $ExportExcel --create-map --map $MapFile
safeset validate $ExportExcel --policy examples/example-policy.yaml
# A no-change local result demonstrates restoration. Do not upload the map.
safeset restore $ExportExcel --map $MapFile --result-column campus --result-column subject --result-column gpa --output $RestoredExcel --authorise
```

The no-change restoration retains coded campus and subject values; it does not
decode them. SafeSet stores no category codebook. An analysis result such as
`record_id` and `team` columns can be restored with `--result-column team` instead.

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

Policy actions: drop, categorical keep, random category code, numeric bin, bounded
exact numeric keep and random source-key pseudonymisation.
Excel workbook and YAML have strict schemas and resource limits. Passing group-size checks
is not evidence of anonymity. This foundation has no independent security audit.
See [architecture](docs/architecture.md), [threat model](docs/threat-model.md),
[safety model](docs/data-safety-model.md), [policy format](docs/policy-format.md),
[implementation plan](docs/development-plan.md) and [verification](docs/verification.md).

From `pwsh`, run `& ./.venv/bin/python -m pytest`, `& ./.venv/bin/ruff check .`,
`& ./.venv/bin/ruff format --check .` and `& ./.venv/bin/python -m build` before
release. `AGENTS.md` and `.github/skills/` support ongoing
Codex and compatible VS Code agent work. Never put real source data into this
checkout, issue reports, agent conversations or test fixtures.
