# How to use SafeSet

SafeSet protects a working copy for analysis, then restores approved results locally. It runs without a network connection.

Passing validation reduces some disclosure risks. It does not prove anonymity or decide whether a copy is suitable to share. Keep source workbooks, private bundles and restored workbooks outside repositories and synchronised folders.

In the macOS app, use **⌘+** and **⌘−** to change text size, or **⌘0** to reset it. The View menu has the same controls. SafeSet remembers your choice.

## Protect a workbook

1. Choose **Protect a workbook** and select the original `.xlsx` file. Select the sheets ChatGPT needs as editable data or reference information. Unselected sheets stay out of the protected copy; the editing workflow preserves them locally when restoring the original workbook.
2. Review the field summary. It initially shows fields needing attention; turn off **Show only fields needing attention** to revisit completed decisions. Use the **X** on a card to remove that field; removed cards appear inactive when all fields are shown, and their undo button restores them. Choose one source identifier per worksheet, then use **Remove undecided fields** to remove all fields that have no action on any selected worksheet. Set actions for other fields needed for analysis before using that shortcut. Removed fields need no classification. Local suggestions explain possible concerns in ordinary language but remain hints only.
3. Choose exactly one source identifier per worksheet for **Replace with random record ID**. SafeSet treats that field internally as a direct identifier used to link records; there is no separate classification picker. Remove other direct identifiers, free text and fields the analysis does not need.
4. Review the values for each **Keep** or **Obfuscate values** field and approve its exact category list. **Group into ranges** needs numeric intervals. **Keep exact number** needs bounds; exact values may still disclose information.
5. Under **What may ChatGPT change?**, leave **Edit selected fields and preserve the original workbook** enabled. Select permitted fields separately for each sheet, such as the team field on Allocations. A sheet with no selected fields is reference only. Keep, Obfuscate values and Keep exact number fields can be editable; identities, grouped ranges, formulas and dates cannot.
6. Set the minimum group size to at least 2. Choose a new protected workbook destination outside a repository, then review the validation summary and editing permissions. Mandatory failures block creation.
7. Approve creation and enter a confirmed passphrase of at least 16 characters. In **What should ChatGPT do?**, describe the analysis or allocation rules using the exact worksheet and field names, without names or student numbers. Then copy the prompt and send it with the protected workbook. This text changes the copied prompt only; it cannot expand editing permissions. Keep the passphrase separately: there is no recovery backdoor. Existing files are never overwritten.

Editing mode creates a version 4 bundle, including for one sheet. Related sheets use shared random entity IDs and separate row IDs. A repeated heading appears once for protection decisions, but editing permissions are chosen separately per sheet. Confirm that the source keys identify the same kind of entity across selected sheets. Selected reference tables still need a source identifier and normal protection decisions; a formula summary without that structure can stay local and recalculate after restoration. Category review retains each worksheet's observed allowlist. To reuse category codes across sheets, explicitly confirm the field under **Shared obfuscation**.

The protected copy omits removed fields and the source identifier. It uses a fresh cryptographically random `record_id`. Obfuscated fields receive fresh random codes per field and export. Equal source categories still have equal codes within that export, so equality and frequency remain visible.

The encrypted bundle defaults to private local storage; you can set its location under Advanced settings. Keep it separate from the protected copy. Turning editing mode off retains the earlier append-results workflow, using version 2 for a single sheet or version 3 for related sheets.

## Choose field classifications

Classify a field by its contents, not by the action you want to use. Never relabel a direct identifier merely to retain it.

For fields you keep, obfuscate or transform, the guided desktop asks why the field is needed. Choose **Information useful for the analysis** for an analytical attribute, or **Information about the person or group that could distinguish them** for a quasi-identifier. **I'm not sure** deliberately remains unresolved and blocks review until you decide to remove the field or choose a supported retained-information role.

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

For a newly structured result workbook, choose **ChatGPT will create a new result
workbook** in the copyable prompt. Work out the rules in ChatGPT. Its returned
workbook may contain different sheets, fields and rows. Keep exact `entity_id`
values on participant rows and include `record_id` only when a result refers to
one particular source row. New team labels may be short result values. Do not
include original names or student numbers; SafeSet adds selected original fields
locally during Restore. Summary sheets may have no participant IDs.

In editing mode, change only the fields listed in the generated prompt. Keep all
record and entity IDs, headings, rows and reference values intact. Use existing
categories or codes and the approved numeric bounds. Do not add sheets or result
columns; put narrative findings in the ChatGPT reply. Known shared codes let an
allocation use a category already present in a reference sheet. New categories,
new fields and participants absent from all protected sheets need a new protection
setup. Participants already present in a protected reference sheet can be added to
an editable target during Restore, using the participant comparison below.

For the earlier append-results mode:

- Preserve every original worksheet, row, heading, `record_id`, `entity_id` and protected value exactly.
- Add short, safe categorical result fields, such as `Team`. Fill every row with a result such as `Campus mismatch` or `No change`; blank result cells are not supported.
- You may add separate analysis worksheets. They may contain blank cells or formulas with saved scalar results. SafeSet reads saved results; it does not calculate or preserve formulas.

Formulas in the original protected worksheets, unsafe text and unsupported spreadsheet content block restoration.

## Restore locally

### Restore a new result workbook

Select **Related sheets or editable workbook bundle**, then **Restore ChatGPT's
new result sheets**. Choose the result workbook, exact original source, matching
private bundle and a new output path. Validate. For each participant result sheet,
choose an original source worksheet and only the fields you want restored. Choose
an `entity_id` join when that source sheet has one row per participant, or an
exact `record_id` join when the result refers to source rows. The default requires
one result row per participant; explicitly allow repeats where the analysis needs
them. Select **Update result joins and review**.

SafeSet checks every referenced ID, exact record-to-entity linkage, source joins,
safe result text and known codebooks. It shows result-sheet and field counts and
counts of new category values. Inspect the returned workbook's assignments,
approve each sheet, field, new-category group and source join, then authorise the
new local workbook. The output contains only the result sheets, with selected
original fields joined to participant rows. Source and returned files are not
overwritten. SafeSet does not determine whether ChatGPT followed your allocation
rules or whether a new team was necessary.

This path supports version 3 or version 4 related-sheet bundles. It accepts static
short result values, blank cells and new category labels. It rejects formulas,
hidden sheets, unknown IDs and invented UUID-shaped codes. Existing protected
worksheets need not be copied into the returned workbook.

### Restore edits or appended results

1. Choose **Restore a workbook**. Select the modified protected copy, the exact original source workbook and the private bundle. Choose a new restored output filename.
2. Enter the passphrase. SafeSet unlocks the bundle locally and checks the original, record coverage, schemas, reference values and permitted changes. A mismatch blocks restoration; SafeSet never guesses an identity.
3. In editing mode, review and approve the changed-cell count for every changed field. The complete proposed workbook is checked before approval. In append-results mode, approve each new result field and analysis sheet.
4. Authorise restoration. Editing mode creates a copy of the original workbook with only the approved field changes applied to the correct records. Other sheets, formatting, charts and original formulas are preserved. Open the result in Excel to recalculate formula summaries; static summaries need their own approved edits. The original is not overwritten. The restored workbook contains identifiers and is sensitive plaintext.

For a version 2 bundle, select every same-schema protected and source worksheet included in the protection run; SafeSet preserves workbook order. For a version 3 relational bundle, the authenticated bundle defines every mandatory worksheet automatically, so the desktop does not show a worksheet picker. After validation, added analysis worksheets appear separately and must each be approved for inclusion. Remove an unwanted added worksheet from the modified protected workbook and validate again. Hidden returned worksheets fail closed.

Version 4 bundles use **Related sheets or editable workbook bundle** on the Restore page, including an editable workbook with only one sheet. This setting is selected automatically after protection. A version 4 bundle binds the entire original file: even a later formatting change to that original requires a new protection run. Existing version 2/3 bundles never acquire editing permissions; start a new protection run to use this workflow.

In version 2/3 append-results mode, source-derived protected fields remain immutable. An altered code, original category, kept value or range label blocks restoration.

### Update participants from a reference sheet

For example, use **Updated Classlist** to decide who belongs in **Allocations**:

1. On Restore, turn on **Compare participants with a membership sheet**. Choose the
   editable sheet to update and a different reference-only membership sheet.
   Both must belong to this version 4 bundle, with one row per participant on each.
2. Choose whether to include reference-only participants and whether to remove
   participants absent from the reference. Removals are off initially.
3. Validate and review. SafeSet shows the additions, removals and existing field
   changes. If assignments are missing, **Copy prompt** supplies instructions for
   ChatGPT to add a **SafeSet additions** proposal sheet. Every original protected
   row must remain intact, including departing participants. The proposal uses
   existing reference `entity_id`s and only the target's editable fields. In
   **What should ChatGPT do?**, state the existing allocation rules using exact
   field names (for example, `Team`, `Role` and `Subject Campus`) and ask for
   valid placements in existing teams first. The copied prompt includes this
   text without changing the authenticated field permissions.
4. Select the workbook returned with those proposals and validate again. For
   other new-row fields, explicitly choose a column from any reference-only sheet
   in the same protected bundle, or **Leave blank**. The selected sheet must have
   exactly one matching row and a value for every new participant. Identity
   matching happens locally. Click **Update comparison
   and review** after changing these choices; no repeated passphrase is needed.
5. Approve additions, removals and changed fields, then authorise local restoration.
   Missing assignments block creation; SafeSet never invents them. You may explicitly
   turn off additions to restore existing participants only.

If the existing teams cannot take every incoming participant under those rules,
ChatGPT must report the unresolved assignments. A typed instruction cannot create
a new team code in the existing protected workbook. New team categories require a
new local protection setup with the intended categories authorised before another
protected copy is shared.

Reference sheets remain unchanged. Participant changes support one plain range or
Excel table, without totals or formulas in its data, and need empty space below
the table to add rows. Merged/hidden data, comments, hyperlinks, data validation
and conditional formatting on the target are not supported for participant changes.
Surviving cells retain their original types and styles. New fields copied from the
reference are literal text; new editable numeric values are numeric cells. Check
summaries and charts in Excel afterwards: fixed formula ranges and static summaries
do not expand automatically. This operation creates a new private workbook and
does not modify the source or the reference worksheets.

In append-results mode, approved analysis worksheets become static tables of cell text, including saved formula results. Formulas, formatting, drawings and charts are not preserved in that mode. IDs inside added worksheets are not replaced with source identities.

## Advanced and CLI

**Advanced tools** include strict YAML policy authoring, technical settings and the earlier version 1 identity-map result join. The CLI offers `protect` and `reconstruct` for version 2, plus legacy `inspect`, `sanitise`, `validate` and `restore`. A version 1 map cannot perform full source reconstruction; there is no implicit conversion.

See [README.md](README.md) for a synthetic CLI example and [policy format](docs/policy-format.md) for the schema. For CLI reconstruction, approve each added worksheet with a repeatable `--analysis-sheet 'Worksheet name'` option. Single-sheet reconstruction also needs `--sheet 'Protected worksheet'` when the returned workbook contains added sheets.

The source format is bounded `.xlsx`: 10 MiB compressed, 50,000 rows, 128 columns and 4,096 characters per field. Structured Excel Tables are supported; SafeSet reads only their defined ranges. Hidden content in a selected range, external links, unsafe cells and ambiguous worksheet selection fail closed.

Source formulas use saved scalar results that may be stale. Recalculate and save locally before protection. Store identifiers with leading zeros as text in Excel.
