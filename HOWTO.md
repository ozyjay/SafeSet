# How to use SafeSet

SafeSet prepares a minimised Excel workbook for analysis and can later join approved results
back to one source identifier. It runs locally. Passing validation reduces some
disclosure risks; it does not establish anonymity, legal compliance or whether a
particular recipient is suitable.

Use `pwsh` for the commands below. The storage controls described here are for
macOS and other POSIX systems; Windows mapping permissions are not implemented.
Keep real source data, policies, encrypted maps and restored results in private,
non-synchronised directories outside repositories. Never upload a source Excel workbook,
identity map or restored Excel workbook to an analysis service.

## 1. Install and open the tool

From this checkout, use the active pyenv Python 3.12 or newer:

```pwsh
python3 -m venv .venv
./.venv/bin/Activate.ps1
python3 -m pip install -e .
safeset --help
```

Installation may need package access. Inspection, sanitisation, validation,
restoration and the desktop interface need no network connection. If SafeSet is
already installed in the virtual environment, just activate it. To open the local
desktop interface, run:

```pwsh
safeset desktop
```

## 2. Prepare the source and policy

The source must be a regular `.xlsx` workbook. Select one or more worksheets in
the desktop interface, or repeat `--sheet 'Worksheet name'` on CLI commands.
Each selected sheet needs the same headings in the same order. SafeSet appends
their rows in workbook order in the desktop interface, or `--sheet` order in the
CLI. Overlapping participant keys are rejected, so
filter an updated sheet to new participants before combining cohorts. Store
identifiers as text in Excel to preserve leading zeros. SafeSet reads
text cells exactly and converts numeric cells to decimal text. The
current limits are 10 MiB, 50,000 rows, 128 columns and 4,096 characters per
field. Keep the source file private; `inspect` displays headings and aggregate
characteristics, but no cell samples. Headings may themselves be sensitive.

```pwsh
safeset inspect examples/synthetic_students.xlsx
```

The selected worksheets are used for policy authoring, export and restoration.
Other worksheets are not exported. For a workbook with one visible worksheet,
selection is automatic.

Create a policy for the intended analysis. You can use the desktop **Policy** tab
to load the source headings, choose an action and classification for every column,
set allowed categories or numeric limits, and save a version 2 policy under a new
filename. Category values appear in the interface only if you explicitly request
them locally. Keep a policy for real data outside repositories because headings
and category labels can be sensitive.

For a hand-written policy, use [the synthetic example](examples/example-policy.yaml)
as a guide. The policy must list **every** source heading, with no extras. Select
exactly one direct identifier to `pseudonymise`; SafeSet replaces it with a fresh
random `record_id` and saves the original key only in the encrypted map. Drop other
direct identifiers, free text and unknown fields. Retain only attributes needed
for the analysis. Set `min_group_size` to at least 2.

| Action | Effect |
| --- | --- |
| `drop` | Omits the field from the export. |
| `pseudonymise` | Replaces the one source key with `record_id`. |
| `keep` | Retains only short categories on an explicit allowlist. |
| `code` | Replaces allowed categories with fresh random codes for each export. |
| `bin` | Replaces numbers with labels for declared contiguous intervals. |
| `keep_numeric` | Retains exact plain decimal values within declared bounds and precision. |

`code` and `keep_numeric` require policy version 2. Coding leaves equality and
frequency patterns visible. No codebook is saved, so coded category labels cannot
be decoded later. Exact numeric values may remain distinctive. See the full
[policy format](docs/policy-format.md) before writing a policy manually.

## 3. Inspect, review and export in the desktop interface

1. In **Inspect**, select the source Excel workbook and review the aggregate findings.
2. In **Policy**, create a policy or use one you have already reviewed.
3. In **Export**, select the source and policy. Choose a **new** export Excel workbook filename
   outside repositories. Leave the map destination empty for SafeSet's private
   default directory, or choose a separate private directory.
4. Select **Prepare review**. Read the validation summary, policy decisions and
   both destinations. A failed mandatory check blocks export.
5. Approve the export for its intended recipient, then enter and confirm a unique
   map passphrase of at least 16 characters. Keep the passphrase separately from
   the encrypted map. There is no recovery mechanism if either is lost.

The map and export must be in separate directories. SafeSet does not overwrite
existing files. The map contains only the selected source key and random ID pairs;
it does not retain dropped names, notes or a category codebook.

## 4. Try the CLI with invented data

This example creates private disposable directories outside the checkout. The
included Excel workbook and policy contain invented records. The commands prompt for export
approval and a hidden map passphrase; the passphrase is never a command argument.

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
```

`sanitise` shows the validation summary **before** asking for export approval. It
also shows the map and export destinations. `--create-map` explicitly authorises
creation of an encrypted identity map. If validation fails or you decline, no
export is created. For a script that has its own explicit approval step,
`--approve-export` supplies that approval after validation; it never bypasses a
failed check. A hidden, interactive passphrase prompt is still required.

`validate` checks an existing candidate Excel workbook against the policy. It is useful for
rechecking a saved export, but it does not approve the recipient or create a map.
PowerShell does not stop a script automatically when a native command exits
non-zero; check `$LASTEXITCODE` before a script continues to later steps.

## 5. Analyse and restore results

Send only an export you have decided is suitable for the intended analysis. Keep
the map local and separate. Prepare a returned Excel workbook with `record_id` and at
least one result column, with exactly one row for every exported ID. Result
headings use lowercase `snake_case`. Remove any returned field you do not intend
to restore; every non-ID column must be individually allowlisted.

In the desktop **Restore** tab, choose the returned Excel workbook and select **Read result
columns**. Approve each column to restore, choose the encrypted map and a **new**
private output filename, then enter the map passphrase and separately authorise
restoration.

For a CLI round trip using the unchanged synthetic export as the returned file:

```pwsh
safeset restore $ExportExcel --map $MapFile --result-column campus --result-column subject --result-column gpa --output $RestoredExcel --authorise
```

For a real analysis result, use one `--result-column` option per approved result
field, such as `--result-column team`. `--authorise` explicitly authorises local
re-identification. SafeSet restores only the selected source key and those result
fields; it does not recover dropped columns or decode category codes. It rejects
missing, duplicate, malformed or unknown IDs, extra columns and unsafe returned
values. The restored Excel workbook is sensitive plaintext: keep it private and never upload
it.

## When a step fails

- **Source and policy headings differ:** update the policy for every current
  source heading, or select the correct source and policy pair. Unknown columns
  cannot pass through silently.
- **Validation fails:** review the aggregate findings and minimise or group the
  retained fields more carefully. Small values or joint groups below
  `min_group_size` block export. There is no override.
- **Destination rejected:** choose a new filename in an existing private directory
  outside repositories. Use separate directories for the map and export. A map
  directory must be owned by you and have POSIX mode `0700`.
- **Restoration fails:** check that the returned file contains precisely
  `record_id` plus the allowlisted columns, and every exported ID exactly once.
  Check that you selected the corresponding map and passphrase. SafeSet never
  guesses an identity.

See the [README](README.md), [data safety model](docs/data-safety-model.md) and
[threat model](docs/threat-model.md) for the checks and their limits.
