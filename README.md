# SafeSet

SafeSet is an offline desktop and CLI tool for creating a protected Excel working copy and later reconstructing a new identifiable workbook locally. It reduces some disclosure risks; it does **not** establish anonymity, legal compliance or suitability for a particular recipient.

## Primary desktop workflow

1. Open `SafeSet.app` on macOS and choose **Protect a workbook**. The installed CLI command `safeset desktop` also opens the app.
2. Choose the original `.xlsx` workbook. SafeSet selects its only visible worksheet automatically. For a relational release, explicitly select every worksheet to **protect and include in the protected release**. Unselected worksheets are excluded rather than copied through. The desktop shows all selected worksheet fields together: a literal heading repeated across worksheets appears once with its worksheet scope, while sheet-specific headings remain separate. The pseudonymised source-key fields form one shared entity domain, so equal source IDs receive the same random `entity_id`; every row also receives its own `record_id`. Inspection runs locally and shows counts and field hints, not cell samples.
3. Give **every** field an action. A consolidated field decision applies to every listed worksheet; confirm that same-named fields genuinely have the same meaning. **Remove** needs no classification choice. **Replace with anonymous ID** identifies the one source field used to link records and is treated internally as a direct identifier. For **Obfuscate values**, **Keep**, **Group into ranges** and **Keep exact number**, choose either **Information useful for the analysis**, **Information about the person or group that could distinguish them**, or **I'm not sure**. The last choice remains blocked as needing attention. Category review combines labels for display but retains a separate exact allowlist for each worksheet. For a relational release, SafeSet offers same-named obfuscated fields for explicit shared-codebook confirmation; unconfirmed fields remain independently randomised. Ordinary-language heuristic suggestions remain advisory and never permit release.
4. Choose **Strict** validation (the default) or explicitly choose **Controlled pseudonymisation**. Strict mode blocks rare groups. Controlled pseudonymisation keeps structural and integrity failures mandatory but presents rare per-sheet and linked groups as disclosure warnings. Review the status, warnings, field counts and destinations before approval. SafeSet writes a protected workbook and a separate encrypted version 2 single-sheet or version 3 relational restoration bundle. It never overwrites an existing file.
5. Work with the protected workbook. You may append new result columns such as a synthetic `Team` field and add separate analysis worksheets. Keep every original worksheet, `record_id`, `entity_id`, row, protected column and protected value intact.
6. Choose **Restore a workbook** and select **Multi-sheet relational bundle** for a version 3 release. Do not select relational worksheets: the authenticated private bundle defines every required worksheet automatically. After unlock, SafeSet separately lists every added visible analysis worksheet for explicit approval; a hidden worksheet is rejected. For a version 2 release spanning several same-schema worksheets, select each protected and source worksheet; SafeSet preserves workbook order. Supply the modified protected workbook and original source. The desktop prefills the most recently created or selected private bundle when that file still exists; **Forget remembered bundle** clears this local path preference. SafeSet never remembers its passphrase. Unlock the bundle locally so SafeSet can verify every required worksheet, source row, entity ID, record ID, schema and protected value. Review and explicitly approve each new result field and added analysis worksheet. Authorise creation of a **new** locally reidentified workbook. Added worksheet cell text, including saved scalar formula results, is copied into static tables without formulas or formatting, and IDs inside them are not translated. SafeSet does not calculate formulas. The original file is never modified.

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

Core runtime operations need no network. Installation and building may access package repositories. The macOS desktop uses SwiftUI with a bundled Python engine and needs no separate Python installation when run from `dist/SafeSet.app`. The local ZIP is ad-hoc signed for development; [macOS app build and release instructions](docs/macos-app.md) explain Developer ID signing and notarisation. POSIX private bundle storage is supported. The shared engine now implements restricted Windows NTFS ACL storage; encrypted Windows round-trip verification and native UI wiring remain release gates. See [actual verification results](docs/verification.md).

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


## Protected document workflow (DOCX)

SafeSet now has a conservative DOCX protection foundation for scholarly manuscripts and similar research documents. The document workflow is:

`original DOCX → protected DOCX + private encrypted bundle → external review/work → returned protected DOCX → local restoration`.

The current implementation:

- automatically detects and protects email addresses and ORCID identifiers in Word text and relationship targets;
- accepts explicit local names/identifiers to protect with stable random SafeSet tokens;
- strips common creator/editor/company metadata and custom document properties;
- removes comments when explicitly selected;
- rejects tracked changes, hidden text, embedded/active objects and identifiers split across formatted Word runs;
- requires every original SafeSet token occurrence to survive the returned document before restoration;
- restores protected identities only into a new local DOCX and never guesses missing mappings.

This reduces some disclosure risks but does not certify that a document is anonymous or suitable for a recipient. The operator remains responsible for reviewing the manuscript for participant information, confidential material, figures/images and other context that deterministic protection may not identify.

Use the document CLI while native UI work evolves:

```pwsh
safeset-document inspect ./Draft.docx
safeset-document protect ./Draft.docx --person 'Synthetic Author' --output ./Draft-protected.docx
safeset-document restore ./Returned-protected.docx --bundle ./private/document.enc --output ./Returned-restored.docx
```

The merged macOS SwiftUI shell includes dedicated Protect document and Restore document pages. Windows is a first-class target using a native WinUI 3 shell over the same shared engine; see `windows/README.md`. Windows desktop protection/restoration remains in preview mode pending encrypted round-trip verification and connection to the shared backend. The Windows ACL storage implementation has native integration tests; that evidence alone does not establish an operational document workflow.
