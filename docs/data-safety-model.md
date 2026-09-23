# Data safety model

For the protected working-copy workflow, the original source is the authority
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
After that binding is verified, reconstruction rejects original source cells
with formula-like prefixes or control characters before writing the restored
workbook. Such cells can be in fields omitted from the protected copy. Correcting
them requires a new source, protection run and matching private bundle; the bound
source cannot be edited in place for an existing release.

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

For a relational release, every source row has a unique `record_id` and every
distinct source key in the declared shared entity domain has one reusable random
`entity_id`. Both are excluded from equivalence grouping. Each sheet is assessed
independently, then all retained source-derived values and worksheet participation
are combined into an entity fingerprint for linked-class reporting. Reusing the
entity ID exposes equality and participation by design.

Same-named categorical fields configured with `code` remain independently
randomised by default. In a relational release, the operator may explicitly
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
