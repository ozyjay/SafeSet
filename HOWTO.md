# How to use SafeSet

SafeSet runs locally. A passing validation report reduces some disclosure risks but does not prove anonymity or decide whether a protected copy may be shared. Keep source workbooks, bundles and reconstructed workbooks private, outside repositories and synchronised folders.

## Build and open the macOS app

Use the active pyenv Python 3.12+ in `pwsh`:

```pwsh
python3 -m venv .venv
./.venv/bin/Activate.ps1
python3 -m pip install -e '.[dev,mac-app]'
& ./scripts/build-macos-app.ps1
& ./scripts/smoke-macos-app.ps1
open ./dist/SafeSet.app
```

Installation may need network access. Inspection, protection, validation and restoration do not. The `.app` bundles Python and its dependencies, so end users need no Python setup. The local ZIP is for development; direct distribution requires Developer ID signing and notarisation. See [macOS app instructions](docs/macos-app.md).

## Protect a workbook

1. Choose **Protect a workbook**, then the original `.xlsx` file. SafeSet selects a sole visible worksheet automatically. Choose a worksheet when several are visible. For multiple matching worksheets, use the advanced interface or CLI.
2. Inspect the local field summary. It shows names, types and cardinality; no cell samples. Every field needs an explicit action. Classify fields you keep or replace; removed fields need no classification choice. Heuristic hints are advisory.
3. Choose one direct source identifier for **Replace with anonymous ID**. This creates a fresh cryptographically random `record_id`. Remove other direct identifiers, free text and unnecessary fields. **Keep** and **Obfuscate values** need an explicitly reviewed category allowlist. **Group into ranges** needs numeric intervals. **Keep exact number** needs bounds; it does not limit decimal places, and exact values may disclose information.
4. Set the minimum group size to at least 2. Review the proposed protection. Failed mandatory validation blocks creation. Passing validation is not approval for a recipient. Choose a new protected workbook destination outside a repository.
5. Approve creation and enter a confirmed passphrase of at least 16 characters. SafeSet creates the protected copy and encrypted version 2 restoration bundle. The bundle defaults to private local storage; its location can be set in Advanced settings. Existing files are never overwritten. Keep the passphrase separately; there is no recovery backdoor.

The protected copy omits removed fields and the original source key. Obfuscated values use fresh random codes per field and export. Equal original categories receive equal codes within that export; equality and frequencies remain visible.

## Work with the protected copy

Analyse or modify the protected workbook locally or in an environment you have separately decided is suitable. You can add new result fields, for example `Team`. Keep the original `record_id`, row coverage, original protected headings and their values intact. Current restoration accepts short safe categorical text in new fields. It blocks formula-like values and unsupported spreadsheet content.

## Restore locally

1. Choose **Restore a workbook** and select the modified protected copy, the exact original source workbook and the private bundle. Choose a new restored output filename.
2. Enter the passphrase to unlock the bundle locally. SafeSet needs its encrypted binding and ID map to validate the returned workbook. It checks the selected source content and order, exact record coverage, schemas and all source-derived protected values. Any mismatch blocks restoration; no identity is guessed.
3. Review the count, restored source fields and each new result heading. Approve every new field you intend to import. To omit a field, remove it from the returned workbook and repeat review.
4. Explicitly authorise restoration. SafeSet creates a **new** workbook with all original source fields and the approved new results. The original is never overwritten. This output contains identifiers and is sensitive plaintext.

Editing source-derived protected fields is not yet supported. An altered code, original category, kept value or range label blocks restoration even if the change seems valid. Re-protect the source to start a new round trip after a source edit.

## Advanced and CLI

**Advanced tools** retain strict YAML policy authoring, detailed technical settings and the earlier version 1 identity-map result join. The CLI offers `protect` and `reconstruct` for the new version 2 round trip, alongside the legacy `inspect`, `sanitise`, `validate` and `restore` commands. A version 1 map cannot be used for full source reconstruction; there is no implicit conversion. See [README.md](README.md) for a synthetic CLI example and [policy format](docs/policy-format.md) for schema details.

The source format is bounded `.xlsx`: 10 MiB compressed, 50,000 rows, 128 columns and 4,096 characters per field. Structured Excel Tables are supported, with only their defined ranges read. Hidden content in a selected data range, external links, unsafe cells and ambiguous worksheet selection fail closed. Source formulas use saved scalar results and may be stale; recalculate and save locally before protection. Exact source identifiers needing leading zeros must be stored as text in Excel.
