# How to use SafeSet

SafeSet protects a working copy for analysis, then restores approved results locally. It runs without a network connection.

Passing validation reduces some disclosure risks. It does not prove anonymity or decide whether a copy is suitable to share. Keep source workbooks, private bundles and restored workbooks outside repositories and synchronised folders.

In the macOS app, use **⌘+** and **⌘−** to change text size, or **⌘0** to reset it. The View menu has the same controls. SafeSet remembers your choice.

## Protect a workbook

1. Choose **Protect a workbook** and select the original `.xlsx` file. SafeSet selects a sole visible worksheet automatically. If several are visible, select every related worksheet in this release.
2. Review the field summary. Choose an action for every field, and classify every field you keep or replace. Removed fields need no classification. The suggested classifications are only hints.
3. Choose exactly one direct source identifier per worksheet for **Replace with random record ID**. Remove other direct identifiers, free text and fields the analysis does not need.
4. Review the values for each **Keep** or **Obfuscate values** field and approve its exact category list. **Group into ranges** needs numeric intervals. **Keep exact number** needs bounds; exact values may still disclose information.
5. Set the minimum group size to at least 2. Choose a new protected workbook destination outside a repository, then review the validation summary. Mandatory failures block creation.
6. Approve creation and enter a confirmed passphrase of at least 16 characters. Keep the passphrase separately: there is no recovery backdoor. Existing files are never overwritten.

When you select multiple worksheets, SafeSet creates a relational protected workbook and version 3 bundle. They use shared random entity IDs and separate row IDs. A repeated heading appears once in the summary, and its decision applies to every listed worksheet. Confirm that same-named fields really mean the same thing. Category review combines the labels but retains an exact allowlist for each worksheet. The summary shows names, types and cardinality, never cell samples.

The protected copy omits removed fields and the source identifier. It uses a fresh cryptographically random `record_id`. Obfuscated fields receive fresh random codes per field and export. Equal source categories still have equal codes within that export, so equality and frequency remain visible.

SafeSet also creates an encrypted version 2 restoration bundle for a single-sheet release. The bundle defaults to private local storage; you can set its location under Advanced settings. Keep the bundle separate from the protected copy.

## Choose field classifications

Classify a field by its contents, not by the action you want to use. Never relabel a direct identifier merely to retain it.

### Direct identifier

Names, student numbers, email addresses, phone numbers and usernames identify or contact someone. **Remove** them, except for exactly one source identifier per worksheet selected for **Replace with random record ID**.

### Quasi-identifier

Campus, cohort, year level, age band and postcode can distinguish someone when combined with other fields. Remove, keep, obfuscate, group into ranges or keep as a bounded exact number only when the analysis needs them.

### Analytical attribute

Preference rank, score, capacity, mark and allocation constraints help perform or interpret the analysis. They have the same available actions as quasi-identifiers.

### Free text, unknown and existing pseudonyms

Remove unconstrained notes, comments and feedback as **Free text**. Remove **Unknown** fields until their meaning and necessity are established. Remove existing pseudonymous source identifiers; SafeSet creates fresh `record_id` and, where needed, `entity_id` values.

Classification does not make a value safe or anonymous. Both quasi-identifiers and analytical attributes enter per-field and combined-group disclosure checks. Keep only the fields the analysis needs.

## Work with the protected copy

Analyse the protected workbook locally or in an environment you have separately decided is suitable.

- Preserve every original worksheet, row, heading, `record_id`, `entity_id` and protected value exactly.
- Add short, safe categorical result fields, such as `Team`. Fill every row with a result such as `Campus mismatch` or `No change`; blank result cells are not supported.
- You may add separate analysis worksheets. They may contain blank cells or formulas with saved scalar results. SafeSet reads saved results; it does not calculate or preserve formulas.

Formulas in the original protected worksheets, unsafe text and unsupported spreadsheet content block restoration.

## Restore locally

1. Choose **Restore a workbook**. Select the modified protected copy, the exact original source workbook and the private bundle. Choose a new restored output filename.
2. Enter the passphrase. SafeSet unlocks the bundle locally and checks source content and order, exact record coverage, schemas and every source-derived protected value. A mismatch blocks restoration; SafeSet never guesses an identity.
3. Review the record count, source fields to restore, new result headings and added analysis worksheets. Approve each new field and worksheet explicitly. To exclude one, remove it from the returned workbook and repeat the review.
4. Authorise restoration. SafeSet creates a **new** workbook containing the source fields and approved results. The original is not overwritten. The restored workbook contains identifiers and is sensitive plaintext.

For a version 2 bundle, select every same-schema protected and source worksheet in the release; SafeSet preserves workbook order. For a version 3 relational bundle, every bundle-bound worksheet is mandatory and selected automatically. You may deselect added analysis worksheets you do not want in the output.

Do not edit source-derived protected fields. An altered code, original category, kept value or range label blocks restoration, even if the change seems valid. Re-protect the source to start a new round trip after a source edit.

Approved analysis worksheets become static tables of cell text, including saved formula results. Formulas, formatting, drawings and charts are not preserved. IDs inside these added worksheets are not replaced with source identities. Put row-level findings in new columns on the original protected worksheets if they must appear beside restored source records.

## Advanced and CLI

**Advanced tools** include strict YAML policy authoring, technical settings and the earlier version 1 identity-map result join. The CLI offers `protect` and `reconstruct` for version 2, plus legacy `inspect`, `sanitise`, `validate` and `restore`. A version 1 map cannot perform full source reconstruction; there is no implicit conversion.

See [README.md](README.md) for a synthetic CLI example and [policy format](docs/policy-format.md) for the schema. For CLI reconstruction, approve each added worksheet with a repeatable `--analysis-sheet 'Worksheet name'` option. Single-sheet reconstruction also needs `--sheet 'Protected worksheet'` when the returned workbook contains added sheets.

The source format is bounded `.xlsx`: 10 MiB compressed, 50,000 rows, 128 columns and 4,096 characters per field. Structured Excel Tables are supported; SafeSet reads only their defined ranges. Hidden content in a selected range, external links, unsafe cells and ambiguous worksheet selection fail closed.

Source formulas use saved scalar results that may be stale. Recalculate and save locally before protection. Store identifiers with leading zeros as text in Excel.
