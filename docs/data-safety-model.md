# Data safety model

## Windows private artefact storage

On Windows, private bundle directories must have a current-user owner and a
protected, explicit NTFS ACL. Only full-control allow entries for that user and
optionally SYSTEM/Administrators are accepted; inheritance and other ACEs fail
closed. New directories and staged files receive private ACLs at creation, before
payload bytes are written. Existing permissive directories are rejected, not
repaired. Select a new private bundle subdirectory separate from the export
directory; SafeSet creates it only as part of explicitly approved publication.

All Windows publications use private staged files and no-clobber hard links.
Private bundle reads also check the parent directory and reject multiply linked
files. Reparse paths, alternate streams and unsupported/nonlocal volumes are
rejected. These controls reduce local access exposure, not disclosure through a
shared document. They do not identify ordinary cloud-synchronised directories,
provide secure deletion or replace human review. Native ACL tests have passed;
encrypted Windows workflow verification is still outstanding and the WinUI
publication controls remain disabled.

For the version 2/3 protected working-copy workflow, the original source is the authority
for all source fields during reconstruction. Every protected source-derived field
must still equal its expected value under the bound policy and random codebook.
New result columns need explicit heading allowlisting and safe cell text; they are
added only to the new local sensitive workbook. Added analysis worksheets are
separate untrusted results: each needs explicit approval and must be a bounded
table containing only short safe text or blank cells. A formula is accepted only
in an added analysis worksheet, only when the workbook contains a saved scalar
result that passes the same cell checks. SafeSet does not calculate the formula
and copies only that saved result into a new static table; a saved empty-string
result becomes a blank cell. Formulas remain
forbidden in bundle-bound returned worksheets. Formatting and drawings are not
preserved.
For relational restoration, the authenticated version 3 bundle—not a desktop
checkbox selection—defines the required worksheet set. Every additional visible
worksheet is treated as an added analysis worksheet. Hidden returned worksheets
are rejected so content cannot evade the added-worksheet review.
Pseudonymous IDs in an added worksheet are not replaced with source identities.
This check prevents accidental source overwrite but cannot establish that an
approved result is accurate or that the protected workbook is suitable for a
recipient. The source-table fingerprint binds the selected data and order, so even
benign source edits require a new protection run.
After that binding is verified, reconstruction copies original source fields,
including fields removed from the protected copy, into a new local workbook.
The writer explicitly marks every output cell as text, so a formula-like prefix
in an original source value is copied as literal text. Control characters in
source values still block restoration. Correcting a blocked cell requires a new
source, protection run and matching private bundle; the bound source cannot be
edited in place for an existing protected workbook. The local source-text locator verifies
the source against the authenticated bundle and shows a count and up to 20
coordinates of blocking control characters. It never sends cell contents to
the desktop UI.

Version 4 editable workbooks bind per-sheet editing permissions and the complete
original file inside the encrypted bundle. The original remains authoritative for
identities, reference fields and local-only worksheets. Only explicitly selected
reversible fields can change: observed categorical values, known category codes
(including explicitly shared codebooks) and bounded numeric values. Disclosure
validation on the protected workbook is unchanged. Missing, duplicate or unknown
record IDs, changed entity links and unapproved field changes still block restore.
No new rows, fields or sheets are accepted by this mode.

Version 5 binds explicitly confirmed source regions to separate logical protected
worksheets. Each region is independently classified and validated. Overlapping
regions, partial Excel Tables, hidden or merged data inside a selected region,
unreviewed fields and stale source files block publication. Unselected source
content stays local and is preserved in a new restored copy. Region suggestions
are advisory and contain coordinates only; they never grant export permission.

The separate result-workbook path can create different sheets, fields and rows.
It uses the original only for authenticated entity/record joins and source fields
explicitly selected by the operator. Original protected rows are not required in
the returned workbook. Known codes are decoded through their bound field domain;
new short labels are reviewed as result categories. The validation review shows
counts and headings, never returned cell values, identities or codebooks. Unknown
identities, ambiguous joins and invented UUID-shaped codes block publication.

Restoration reviews changed-cell counts per field and requires explicit approval
for every changed field. It applies those values to a copy of the original package,
preserving local worksheets, original formulas and formatting. The package binding
also covers local-only content and formatting, so changes to the original invalidate
review. Source numeric cells remain numeric only when edited values fit Excel's
15 significant-digit precision; numeric source strings remain text. Formula
calculation is requested on opening in Excel, never performed by SafeSet. Static
summaries may become inconsistent unless separately selected and edited. A valid
change can still be an incorrect allocation; validation cannot judge its meaning.

A **direct identifier** connects a record to a person; a **pseudonymous identifier**
is the generated random `record_id`. A **quasi-identifier** may identify someone in
combination with other attributes. An **analytical attribute** serves an approved
analysis but can still disclose information. **Free text** is unconstrained prose;
**unknown** fields are unclassified. Unknown fields and free text cannot be retained.
Direct identifiers must be dropped except the single source key used in the map.
The guided desktop records that source-key choice as `direct_identifier`
automatically. Its plain-language retained-information choices map to
`analytical_attribute` and `quasi_identifier`; **I'm not sure** remains unresolved
and blocks protection.

Source Excel date/time cells are read as ISO text so they can be inspected and
explicitly dropped or transformed under the policy. Exact date-shaped labels
remain ineligible for categorical retention. Inspection is advisory: column-name heuristics, inferred types, cardinality,
small-category counts, date/precise-number flags, identifier shapes and text
heuristics guide local review. It prints no sample values. These heuristics are
incomplete; absence of a finding is not permission to keep a column.

Validation checks exact columns, non-empty datasets, canonical unique UUIDv4 IDs,
policy output domains, identifier-shaped values, prose/control/formula hazards,
per-column small cells and joint equivalence classes across all retained non-ID
attributes. `min_group_size` is mandatory and at least 2. A small cell or joint
class blocks export. Reports show counts only, never category values or class
members. Reports include minimum class size, unique-record count and fraction,
small-class record count, and high-cardinality warnings. This is a configurable
k-style diagnostic, not a formal privacy guarantee. IDs are excluded from grouping.

Strict validation is the default and retains that blocking behaviour. Under the
explicit `controlled_pseudonymisation` profile, small cells and small joint or
linked classes are warnings requiring review rather than mandatory failures.
Unexpected fields, unsafe values, direct/free-text retention, domain violations,
malformed identifiers and restoration-integrity failures still block export with
no override. This profile accepts additional residual disclosure risk for a
controlled pseudonymised use; it does not establish anonymity.

For a relational workbook, every source row has a unique `record_id` and every
distinct source key in the declared shared entity domain has one reusable random
`entity_id`. Both are excluded from equivalence grouping. Each sheet is assessed
independently, then all retained source-derived values and worksheet participation
are combined into an entity fingerprint for linked-class reporting. Reusing the
entity ID exposes equality and participation by design.

Same-named categorical fields configured with `code` remain independently
randomised by default. In a relational workbook, the operator may explicitly
confirm an eligible heading as one shared category domain. Exact matching source
labels then receive the same fresh random code in every selected worksheet where
that heading is coded. This exposes cross-worksheet category equality and
frequency, is recorded in the authenticated bundle and produces a validation
warning. SafeSet does not infer semantic equivalence from a heading.

Categorical allowlists, numeric bounds and bin intervals are deliberate
minimisation boundaries.
Keep values must be non-empty short labels (at most 64 characters and four words),
with no identifier/date/formula shapes. This sacrifices flexibility to avoid silent
free-text passthrough. Blank categorical values and out-of-range numeric values fail.
For `keep_numeric`, a genuinely blank source cell remains blank; whitespace-only
text still fails. Blank numeric cells participate in per-field and joint group
checks because the missingness pattern can itself disclose information.
Finite bins are contiguous, increasing and non-overlapping: left-inclusive and
right-exclusive except that the final upper endpoint is included. Labels are
`[lower, upper)` and `[lower, upper]` respectively.

Version 2 can replace allowed categorical values with fresh random codes. This
hides their labels while preserving equality and frequency patterns within each
column; it does not remove linkability through those patterns. In the legacy
version 1 map workflow the codebook is ephemeral. The protected working-copy
workflow encrypts observed codebooks inside the version 2 restoration bundle.
Version 3 policies can retain exact plain decimal values within policy bounds and
do not impose a decimal-place limit. Version 2 policies retain their original
configured precision check. Exact numbers may form rare groups and increase
disclosure risk; the same per-field and joint checks apply. The validation report
warns when either action is used.
During legacy authorised local restoration, original labels for coded fields can be read
from the original source workbook with exact source-key coverage and matching
category/code groupings. Dropped fields remain absent. The encrypted map does not
store a codebook or source snapshot, so this check cannot prove the selected source
workbook has not changed since export. The version 2 bundle instead binds the
normalised source table and stores observed codebooks for reconstruction.

No check measures auxiliary-data attacks, within-group sensitive-attribute
homogeneity, longitudinal linkage or the suitability of a particular AI service.
Human review and purpose limitation remain mandatory. No automatic suppression,
privacy budget, probabilistic inference, redaction or safety override exists.


## Participant comparison during Restore

Participant comparison during workbook Restore is local reconciliation, not a
new disclosure assessment. It uses only participants already represented in the
authenticated protected reference sheet. SafeSet validates entity linkage and
assignment domains; it does not determine whether a reference list is current or
whether an assignment is substantively correct. Added identities and explicitly
mapped local reference values appear only in the new sensitive local workbook. A
field source may be any authenticated reference-only sheet with unique, complete
entity coverage and selected field values for the incoming participants. Original
protected rows remain mandatory, and additions/removals need explicit review.
The reference worksheets remain unchanged. Static summaries and fixed formula or
chart ranges need local review after participant counts change.

## Document protection model

The DOCX workflow uses a separate protection model from spreadsheet policies. It does not infer that a manuscript is safe because no identifier pattern was found.

Operator-provided identity strings are exact local matches. SafeSet also detects email and ORCID shapes in supported Word text parts and relationship attributes. Each protected value receives a fresh random document-scoped token; repeated occurrences of the same value use the same token so the scholarly document remains coherent during external review. The encrypted document bundle records the original value, token, kind and expected occurrence count.

Common authoring metadata and custom document properties are removed rather than tokenised. Comments can be removed. Tracked changes, hidden text, embedded/active content and protected identities split across Word formatting runs fail closed in the first iteration.

Restoration verifies the returned DOCX before writing anything. Every token must occur exactly as many times as recorded in the bundle, and none of the original protected values may already be present. Restoration replaces only the authenticated tokens and publishes a new local document without overwriting the returned copy.

These checks do not detect indirect identification, participant information expressed without a known identifier shape, confidential research content, identifying figures/images, acknowledgements or contextual clues. Human purpose/suitability review remains mandatory.
