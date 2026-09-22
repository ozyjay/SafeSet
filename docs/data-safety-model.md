# Data safety model

A **direct identifier** connects a record to a person; a **pseudonymous identifier**
is the generated random `record_id`. A **quasi-identifier** may identify someone in
combination with other attributes. An **analytical attribute** serves an approved
analysis but can still disclose information. **Free text** is unconstrained prose;
**unknown** fields are unclassified. Unknown fields and free text cannot be retained.
Direct identifiers must be dropped except the single source key used in the map.

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

Categorical allowlists, numeric bounds and bin intervals are deliberate
minimisation boundaries.
Keep values must be non-empty short labels (at most 64 characters and four words),
with no identifier/date/formula shapes. This sacrifices flexibility to avoid silent
free-text passthrough. Blank retained values and out-of-range numeric values fail.
Finite bins are contiguous, increasing and non-overlapping: left-inclusive and
right-exclusive except that the final upper endpoint is included. Labels are
`[lower, upper)` and `[lower, upper]` respectively.

Version 2 can replace allowed categorical values with fresh random codes. This
hides their labels while preserving equality and frequency patterns within each
column; it does not remove linkability through those patterns. The codebook is
ephemeral. Version 2 can retain exact plain decimal values within policy bounds
and precision. Exact numbers may form rare groups and increase disclosure risk;
the same per-field and joint checks apply. The validation report warns when either
action is used.
During authorised local restoration, original labels for coded fields can be read
from the original source workbook with exact source-key coverage and matching
category/code groupings. Dropped fields remain absent. The encrypted map does not
store a codebook or source snapshot, so this check cannot prove the selected source
workbook has not changed since export.

No check measures auxiliary-data attacks, within-group sensitive-attribute
homogeneity, longitudinal linkage or the suitability of a particular AI service.
Human review and purpose limitation remain mandatory. No automatic suppression,
privacy budget, probabilistic inference, redaction or safety override exists.
