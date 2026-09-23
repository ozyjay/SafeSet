# How to use SafeSet

SafeSet runs locally. A passing validation report reduces some disclosure risks but does not prove anonymity or decide whether a protected copy may be shared. Keep source workbooks, bundles and reconstructed workbooks private, outside repositories and synchronised folders.

## Protect a workbook

1. Choose **Protect a workbook**, then the original `.xlsx` file. SafeSet selects a sole visible worksheet automatically. When several are visible, select every related worksheet that belongs to the release and configure each one separately. Selecting multiple worksheets creates a relational protected workbook and version 3 bundle with shared random entity IDs and separate row IDs.
2. Inspect the local field summary. It shows names, types and cardinality; no cell samples. Every field needs an explicit action. Classify fields you keep or replace; removed fields need no classification choice. Heuristic hints are advisory.
3. Choose one direct source identifier for **Replace with anonymous ID**. This creates a fresh cryptographically random `record_id`. Remove other direct identifiers, free text and unnecessary fields. **Keep** and **Obfuscate values** need an explicitly reviewed category allowlist. **Group into ranges** needs numeric intervals. **Keep exact number** needs bounds; it does not limit decimal places, and exact values may disclose information.
4. Set the minimum group size to at least 2. Review the proposed protection. Failed mandatory validation blocks creation. Passing validation is not approval for a recipient. Choose a new protected workbook destination outside a repository.
5. Approve creation and enter a confirmed passphrase of at least 16 characters. SafeSet creates the protected copy and encrypted version 2 restoration bundle. The bundle defaults to private local storage; its location can be set in Advanced settings. Existing files are never overwritten. Keep the passphrase separately; there is no recovery backdoor.

The protected copy omits removed fields and the original source key. Obfuscated values use fresh random codes per field and export. Equal original categories receive equal codes within that export; equality and frequencies remain visible.

## Choose field classifications

Classify a field according to what it contains, not according to the action you
want SafeSet to permit. Never relabel a direct identifier as a quasi-identifier
or analytical attribute merely to retain it.

| Classification | Use it for | Permitted treatment |
| --- | --- | --- |
| **Direct identifier** | A value that directly identifies or contacts someone, such as a student number, name, email address, phone number or username | **Remove**, or choose exactly one source identifier per worksheet for **Replace with anonymous ID** |
| **Quasi-identifier** | A value that may distinguish someone when combined with other information, such as campus, cohort, course, year level, age band or postcode | Remove, keep, obfuscate, group into ranges or keep as a bounded exact number |
| **Analytical attribute** | Information genuinely required to perform or interpret the analysis, such as preference rank, score, capacity, mark or allocation constraint | The same actions as a quasi-identifier |
| **Free text** | Unconstrained notes, comments, feedback, explanations or descriptions | **Remove only** |
| **Unknown** | A field whose meaning, necessity or sensitivity has not been established | **Remove only** until it has been assessed |
| **Pseudonymous identifier** | An existing artificial identifier that still links records or may be mapped back elsewhere | Source fields should be removed; SafeSet creates fresh `record_id` and `entity_id` values where needed |

Use this decision sequence for each source field:

1. If it directly identifies or contacts the person, choose **Direct identifier**.
2. If it contains unconstrained prose, choose **Free text** and remove it.
3. If it is genuinely required to perform or interpret the allocation analysis,
   choose **Analytical attribute**.
4. If it may help distinguish a person, especially when combined with other
   fields, choose **Quasi-identifier**.
5. If its meaning or necessity is unclear, choose **Unknown** and remove it until
   it has been assessed.

Typical student-allocation examples are:

- Student number, name and email address: **Direct identifier**.
- Campus, cohort and year level: usually **Quasi-identifier**.
- Preference rank, score and allocation outcome: usually **Analytical attribute**.
- Adviser comments and student notes: **Free text**.

Classification does not make a value safe or anonymous. Quasi-identifiers and
analytical attributes both enter SafeSet's per-field and combined-group disclosure
checks. An analytical classification is not an exemption from those checks or from
the need to minimise the released fields.

## Work with the protected copy

Analyse or modify the protected workbook locally or in an environment you have separately decided is suitable. You can add new result fields, for example `Team`, and separate analysis worksheets. Keep every original worksheet, `record_id`, `entity_id`, row, protected heading and protected value intact. Current restoration accepts short safe categorical text in new fields. Give every row a result such as `Campus mismatch` or `No change`; blank result cells are not supported. Added analysis worksheets may contain blank cells and formulas with saved scalar results. SafeSet does not calculate or preserve formulas: it validates the saved results as short safe text and copies them into a static output table. Formulas in original protected worksheets, unsafe text and unsupported spreadsheet content are blocked.

## Restore locally

1. Choose **Restore a workbook** and select the modified protected copy, the exact original source workbook and the private bundle. Choose a new restored output filename.
2. Enter the passphrase to unlock the bundle locally. SafeSet needs its encrypted binding and ID map to validate the returned workbook. It checks the selected source content and order, exact record coverage, schemas and all source-derived protected values. Any mismatch blocks restoration; no identity is guessed.
3. Review the count, restored source fields, each new result heading and every added analysis worksheet. Every detected result field and worksheet must be explicitly approved; remove unwanted items from the returned workbook and repeat review.
4. Explicitly authorise restoration. SafeSet creates a **new** workbook with all original source fields and the approved new results. The original is never overwritten. This output contains identifiers and is sensitive plaintext.

Editing source-derived protected fields is not yet supported. An altered code, original category, kept value or range label blocks restoration even if the change seems valid. Re-protect the source to start a new round trip after a source edit.

Approved analysis worksheet cell text, including saved formula results, is copied
into static tables in the new sensitive workbook. Formulas, formatting, drawings
and charts are not preserved. SafeSet does not calculate formulas. SafeSet
does not replace `record_id` or `entity_id` values inside those worksheets with
source identities. Put row-level findings in new columns on the original protected
worksheets when they need to appear beside restored source records.

## Advanced and CLI

**Advanced tools** retain strict YAML policy authoring, detailed technical settings and the earlier version 1 identity-map result join. The CLI offers `protect` and `reconstruct` for the new version 2 round trip, alongside the legacy `inspect`, `sanitise`, `validate` and `restore` commands. A version 1 map cannot be used for full source reconstruction; there is no implicit conversion. See [README.md](README.md) for a synthetic CLI example and [policy format](docs/policy-format.md) for schema details.

For CLI reconstruction, approve each added worksheet with a repeatable
`--analysis-sheet 'Worksheet name'` option. Single-sheet reconstruction also needs
`--sheet 'Protected worksheet'` when the returned workbook contains added sheets.

The source format is bounded `.xlsx`: 10 MiB compressed, 50,000 rows, 128 columns and 4,096 characters per field. Structured Excel Tables are supported, with only their defined ranges read. Hidden content in a selected data range, external links, unsafe cells and ambiguous worksheet selection fail closed. Source formulas use saved scalar results and may be stale; recalculate and save locally before protection. Exact source identifiers needing leading zeros must be stored as text in Excel.
