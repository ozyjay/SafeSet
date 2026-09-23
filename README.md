# SafeSet

SafeSet is an offline desktop and CLI tool for creating a protected Excel working copy and later reconstructing a new identifiable workbook locally. It reduces some disclosure risks; it does **not** establish anonymity, legal compliance or suitability for a particular recipient.

## Primary desktop workflow

1. Open `SafeSet.app` on macOS and choose **Protect a workbook**. The installed CLI command `safeset desktop` also opens the app.
2. Choose the original `.xlsx` workbook. SafeSet selects its only visible worksheet automatically. For a relational release, explicitly select every related worksheet and configure each one. The pseudonymised source-key fields form one shared entity domain, so equal source IDs receive the same random `entity_id`; every row also receives its own `record_id`. Inspection runs locally and shows counts and field hints, not cell samples.
3. Give **every** field an action. Classify fields you keep or replace; **Remove** needs no classification choice. Use **Replace with anonymous ID** for exactly one source key, **Obfuscate values**, **Keep**, **Group into ranges** or **Keep exact number**. Review category allowlists and numeric settings explicitly. For a relational release, SafeSet offers same-named obfuscated fields for explicit shared-codebook confirmation; unconfirmed fields remain independently randomised. Heuristic hints do not make decisions for you.
4. Choose **Strict** validation (the default) or explicitly choose **Controlled pseudonymisation**. Strict mode blocks rare groups. Controlled pseudonymisation keeps structural and integrity failures mandatory but presents rare per-sheet and linked groups as disclosure warnings. Review the status, warnings, field counts and destinations before approval. SafeSet writes a protected workbook and a separate encrypted version 2 single-sheet or version 3 relational restoration bundle. It never overwrites an existing file.
5. Work with the protected workbook. You may append new result columns such as a synthetic `Team` field and add separate analysis worksheets. Keep every original worksheet, `record_id`, `entity_id`, row, protected column and protected value intact.
6. Choose **Restore a workbook** and select **Multi-sheet relational bundle** for a version 3 release. Supply the modified protected workbook, original source and bundle. Unlock the bundle locally so SafeSet can verify every selected worksheet, source row, entity ID, record ID, schema and protected value. Review and explicitly approve each new result field and added analysis worksheet. Authorise creation of a **new** locally reidentified workbook. Added worksheet cell text is copied into static tables without formatting, and IDs inside them are not translated. The original file is never modified.

Classify a field according to what it contains, not according to the action you
want SafeSet to permit. In particular, never relabel a direct identifier as a
quasi-identifier or analytical attribute merely to retain it. See the
[field-classification guide](HOWTO.md#choose-field-classifications) for the full
decision sequence and student-allocation examples.

Reconstruction restores source fields from the exact original workbook, including fields removed from the protected copy. New result fields are imported only when approved. Changes to source-derived protected fields, including coded categories, are blocked. Result cells currently accept only short, safe categorical text. Editable source-derived fields are not supported in this version.

The private bundle contains the selected source key map, observed category codebooks, policy decisions and a source binding, not whole source rows or dropped personal fields. It is encrypted with Argon2id and Fernet. Keep the passphrase and bundle separately and privately. The source workbook, bundle and restored output are sensitive and must stay outside repositories and cloud-synchronised folders. The protected workbook may still disclose information through attributes, equality and frequencies.

**Advanced tools** in the desktop retain policy YAML authoring and the earlier selected-result join. The CLI supports the new `protect` and `reconstruct` commands with explicit YAML policy and result-field options. It also retains the version 1 `sanitise` and `restore` commands. Version 1 maps are not accepted by reconstruction; no automatic migration occurs.

## Set up

Use the active pyenv Python 3.12+ from `pwsh`:

```pwsh
python3 -m venv .venv
./.venv/bin/Activate.ps1
python3 -m pip install -e '.[dev,mac-app]'
& ./scripts/build-macos-app.ps1
& ./scripts/smoke-macos-app.ps1
```

Core runtime operations need no network. Installation and building may access package repositories. The macOS desktop uses SwiftUI with a bundled Python engine and needs no separate Python installation when run from `dist/SafeSet.app`. The local ZIP is ad-hoc signed for development; [macOS app build and release instructions](docs/macos-app.md) explain Developer ID signing and notarisation. POSIX private bundle storage is supported; Windows ACL protection has not been implemented.

## CLI and synthetic example

The technical CLI accepts a strict YAML policy for protection. Its `protect` command creates a version 2 bundle; `reconstruct` needs the original source and an explicit `--result-column` for every new field. Use synthetic fixtures only in a checkout; keep operational data outside it.

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
safeset protect examples/synthetic_students.xlsx --policy examples/example-policy.yaml --output $ExportExcel --create-bundle --bundle $MapFile
safeset validate $ExportExcel --policy examples/example-policy.yaml
# The unchanged protected workbook demonstrates local reconstruction.
safeset reconstruct $ExportExcel --original-source examples/synthetic_students.xlsx --bundle $MapFile --output $RestoredExcel --authorise
```

CLI protection requires validation, review, explicit approval and hidden passphrase entry. Reconstruction requires exact IDs, approval of every new result field and explicit authorisation. The legacy `sanitise` and `restore` commands still create a version 1 map and perform a selected-result join.

For related worksheets with distinct schemas, provide one policy per sheet. The
left side of each `--sheet-policy` is the literal worksheet name. Every policy's
pseudonymised source key is placed in the same explicit entity domain:

```pwsh
safeset protect-relational source.xlsx `
  --sheet-policy 'Enrolments=enrolments-policy.yaml' `
  --sheet-policy 'Preferences=preferences-policy.yaml' `
  --shared-code-field Cohort `
  --validation-profile controlled_pseudonymisation `
  --output protected.xlsx --create-bundle --bundle relational.enc

safeset reconstruct-relational returned.xlsx `
  --original-source source.xlsx --bundle relational.enc `
  --output restored.xlsx `
  --result-column 'Enrolments=Team' `
  --result-column 'Preferences=Team' --authorise
```

The CLI reports validation before prompting for approval or publishing. Omit
`--validation-profile` for strict mode. Controlled pseudonymisation changes only
rare-group findings into warnings; it does not bypass schema or integrity failures.
Repeat `--shared-code-field` only for same-named coded fields that genuinely use
one category domain across worksheets. Without explicit confirmation, even
same-named obfuscated fields receive independent random codes. During reconstruction,
use repeatable `--analysis-sheet` options to approve every added analysis worksheet.

See [HOWTO.md](HOWTO.md), [architecture](docs/architecture.md), [threat model](docs/threat-model.md), [safety model](docs/data-safety-model.md), [policy format](docs/policy-format.md) and [verification](docs/verification.md).

SafeSet writes fixed, value-free local diagnostics to `~/.local/state/safeset/diagnostics.log`; `safeset log-path` shows that path. Never put real student data, credentials, bundles, source workbooks or restored outputs in this repository or an agent conversation.
