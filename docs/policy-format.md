# Policy versions 1, 2 and 3

Version 5 *restoration bundles* add confirmed workbook-region coordinates to the
version 4 editable workflow. Each logical region uses an ordinary strict version 3
policy with exact headings. Region selection and editing permissions are workflow
configuration, not YAML keys. Older bundles remain readable and are not upgraded.

Version 4 *restoration bundles* add editable-workbook permissions without changing
policy YAML. The desktop protocol accepts `editable_fields` as a mapping containing
every selected worksheet and a list of its editable source headings (empty for a
reference sheet). Unknown sheets/fields, duplicates and non-string headings fail.
Only `keep`, `code` and `keep_numeric` actions can be selected; identifiers, dropped
fields, bins, formula cells and date cells are excluded. These fields still undergo
the same protection and disclosure checks.

The encrypted bundle records the permissions, observed category domains, codebooks
and original-file digest. Returned categorical edits use observed categories;
codes must belong to the field's authenticated codebook or an explicitly shared
same-field codebook. Numeric edits use the policy's bounds and genuine-blank rule.
Publication of numeric Excel cells also enforces Excel precision. Changed fields
need their own explicit restoration approval. These permissions cannot be added
to old bundles; a new protection run creates a `SAFESET4` envelope. Adding
`editable_fields` to policy YAML remains an unknown-key error.

Participant comparison is an explicit local Restore operation for version 4,
separate from policy YAML and the original editing permissions. It requires one
editable target and one reference-only sheet from the same bundle. Original
returned row coverage remains exact. A selected proposal sheet may supply only
known reference-only entity IDs and target editable values within the authenticated
domains. Local mappings or explicit blank choices supply other new-row fields.
Additions and removals require separate approval; neither creates new codebook
entries, identities or protection permissions. See architecture.md for the bounded
desktop protocol and supported structural workbook layouts.

The guided protected-workbook desktop constructs a strict version 3 policy in
memory from explicit field decisions. Saving YAML is optional. Source-derived protected
fields are immutable during version 2 bundle reconstruction; newly added result
fields need separate explicit approval and are not policy source columns. The
version 2 *restoration bundle* is distinct from policy versions 2 and 3 and legacy
version 1 identity maps.

See `examples/example-policy.yaml`. YAML mappings reject duplicate keys and aliases;
unknown keys and types fail. Top-level keys are exactly `version`, `columns` and
`min_group_size`. The version must be integer 1, 2 or 3; minimum group size an integer
>=2. Version 1 policies retain their original meaning. Version 2 adds `code` and
`keep_numeric`; those actions are rejected under version 1. Version 3 removes the
decimal-place limit from `keep_numeric` while retaining its bounds. The example uses
version 3.
Column names use the source workbook's literal headings. They must be non-empty,
unique, at most 64 characters, have no leading or trailing whitespace, and contain
no control characters. Spaces, punctuation, mixed case and Unicode are supported.
`record_id` is reserved as an exact heading and cannot be a source column.
Source headings must match the policy exactly (order may differ). For structured
Excel Tables, the visible header cells must also match the table's header metadata
exactly.
This relaxation applies to all supported policy versions; existing policies and mappings
retain their meaning and require no migration. Returned result headings obey the
same bounds and still require an explicit allowlist before restoration.

Classifications: `direct_identifier`, `pseudonymous_identifier`, `quasi_identifier`,
`analytical_attribute`, `free_text`, `unknown`. Pseudonymous source fields and
unknown fields can only be dropped. The output `record_id` is always classified as
pseudonymous; existing source pseudonyms are not reused.

The desktop form does not ask for a classification when an action is `drop`.
When it creates a policy from an unclassified removed field, it writes
`classification: unknown` to retain the strict YAML schema. Existing policies
that classify dropped fields remain valid.
The form also does not ask for a classification when an action is `pseudonymise`:
that action selects the source field used to link records, and policy authoring
always writes `classification: direct_identifier`. Retained and transformed
fields use plain-language choices mapped to `analytical_attribute` or
`quasi_identifier`. **I'm not sure** remains an unresolved UI state and cannot be
serialised as an approved policy decision.

| Action | Required configuration | Permitted classification |
| --- | --- | --- |
| `drop` | `action`, `classification` | Any recognised classification |
| `pseudonymise` | `action`, `classification` | Direct identifier only; exactly one |
| `keep` | Plus non-empty, unique string `allowed_values` | Quasi-identifier or analytical attribute |
| `bin` | Plus `bins`: list of at least two `[lower, upper]` numeric pairs | Quasi-identifier or analytical attribute |
| `code` (v2/v3) | Plus non-empty, unique string `allowed_values` | Quasi-identifier or analytical attribute |
| `keep_numeric` (v2) | Plus `bounds: [lower, upper]` and `max_decimal_places` | Quasi-identifier or analytical attribute |
| `keep_numeric` (v3) | Plus `bounds: [lower, upper]` | Quasi-identifier or analytical attribute |

Keep labels must be short categories. Use quoted YAML strings for numbers/booleans.
`code` checks source values against the same strict categorical allowlist, then
replaces each distinct value with a fresh random UUIDv4 code. Matching values in
one column receive the same code within one export; codes differ across columns
and runs. The legacy version 1 map has no category codebook. The new version 2
restoration bundle encrypts only observed category codes. Authorised legacy local restoration can put the
original labels back only when the operator supplies the original source workbook
and policy; it checks exact source-key coverage and category/code grouping. A
changed source workbook with the same keys and grouping cannot be ruled out because
the map contains no source snapshot. The encrypted map still contains only
`record_id` to source-key pairs.

`keep_numeric` preserves a genuinely blank cell as blank. Otherwise, it preserves
the exact numeric value of a plain non-negative decimal within inclusive finite
bounds. Leading and trailing zeros are normalised (for example, `04.20` becomes
`4.2`); signs, whitespace (including whitespace-only cells) and exponent notation
are rejected. A non-blank source string is limited to 64 characters. Version 2
also requires `max_decimal_places`, an integer from 0 to 6, and rejects source
values with greater precision. Version 3 deliberately has no decimal-place limit.
Loading a version 2 policy and saving it from the current desktop writes version 3
and therefore removes that limit; the original file is never overwritten. This
action exposes the exact numeric values and missingness pattern in the export. All
retained fields, including blank numeric cells, coded categories and exact numeric
values, participate in per-field and joint group checks. A passing check is not an
anonymity or recipient-suitability decision.

A heading detected as a direct identifier cannot be kept even if classified as an
analytical attribute. A heading detected as free text must be dropped. For these
checks, punctuation and spaces are treated as word separators. Heuristics
are a backstop, not a universal list. Domain authors must classify unfamiliar
sensitive fields conservatively.

Output columns follow policy order with `record_id` first; dropped columns never
appear. Source keys must be non-empty and unique, and remain exact strings in the
map. Source keys with spreadsheet-formula prefixes or control characters fail
before export so the resulting map remains restorable. Bin labels are limited to
64 characters. There is no `generalise` or `redact` in any version. To add an action or schema option,
follow `.github/skills/policy-schema/SKILL.md`, update examples and migration
behaviour and add rejection tests first.

Validation profiles are workflow configuration, not YAML policy keys. Adding a
`validation_profile` key to any policy remains an unknown-key error.
The relational workflow applies one ordinary strict version 3 policy to each
selected worksheet. Each policy must contain exactly one pseudonymised source key;
those explicitly selected keys form one shared entity domain even when their
headings differ. `record_id` and `entity_id` are reserved relational output
headings and are rejected in relational source schemas.

Shared obfuscation is also workflow configuration, not a policy key. A field may
be explicitly selected for a shared random codebook only when the same literal
heading uses `action: code` in at least two selected worksheet policies. Exact
matching category labels then share a code across those sheets. Matching headings
do not imply sharing: omitted fields keep independent codebooks. The desktop app
offers eligible headings for confirmation; the CLI uses repeatable
`--shared-code-field` options. Adding this setting to policy YAML remains an
unknown-key error.
