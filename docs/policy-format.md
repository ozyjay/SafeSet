# Policy versions 1 and 2

See `examples/example-policy.yaml`. YAML mappings reject duplicate keys and aliases;
unknown keys and types fail. Top-level keys are exactly `version`, `columns` and
`min_group_size`. The version must be integer 1 or 2; minimum group size an integer
>=2. Version 1 policies retain their original meaning. Version 2 adds `code` and
`keep_numeric`; those actions are rejected under version 1. The example uses version 2.
Column names use the source workbook's literal headings. They must be non-empty,
unique, at most 64 characters, have no leading or trailing whitespace, and contain
no control characters. Spaces, punctuation, mixed case and Unicode are supported.
`record_id` is reserved as an exact heading and cannot be a source column.
Source headings must match the policy exactly (order may differ). For structured
Excel Tables, the visible header cells must also match the table's header metadata
exactly.
This relaxation applies to policy versions 1 and 2; existing policies and mappings
retain their meaning and require no migration. Returned result headings obey the
same bounds and still require an explicit allowlist before restoration.

Classifications: `direct_identifier`, `pseudonymous_identifier`, `quasi_identifier`,
`analytical_attribute`, `free_text`, `unknown`. Pseudonymous source fields and
unknown fields can only be dropped. The output `record_id` is always classified as
pseudonymous; existing source pseudonyms are not reused.

| Action | Required configuration | Permitted classification |
| --- | --- | --- |
| `drop` | `action`, `classification` | Any recognised classification |
| `pseudonymise` | `action`, `classification` | Direct identifier only; exactly one |
| `keep` | Plus non-empty, unique string `allowed_values` | Quasi-identifier or analytical attribute |
| `bin` | Plus `bins`: list of at least two `[lower, upper]` numeric pairs | Quasi-identifier or analytical attribute |
| `code` (v2) | Plus non-empty, unique string `allowed_values` | Quasi-identifier or analytical attribute |
| `keep_numeric` (v2) | Plus `bounds: [lower, upper]` and `max_decimal_places` | Quasi-identifier or analytical attribute |

Keep labels must be short categories. Use quoted YAML strings for numbers/booleans.
`code` checks source values against the same strict categorical allowlist, then
replaces each distinct value with a fresh random UUIDv4 code. Matching values in
one column receive the same code within one export; codes differ across columns
and runs. No category codebook is saved, so SafeSet cannot decode those labels
later. The encrypted map still contains only `record_id` to source-key pairs.

`keep_numeric` preserves the exact numeric value of a plain non-negative decimal
within inclusive finite bounds. Leading and trailing zeros are normalised (for
example, `04.20` becomes `4.2`); signs, whitespace and exponent notation are
rejected. `max_decimal_places` is a mandatory integer from 0 to 6; the source
string is limited to 64 characters. This action exposes the exact numeric values
in the export. All retained fields, including coded categories and exact numeric
values, participate in per-field and joint group checks. A passing check is not
an anonymity or recipient-suitability decision.

A heading detected as a direct identifier cannot be kept even if classified as an
analytical attribute. A heading detected as free text must be dropped. For these
checks, punctuation and spaces are treated as word separators. Heuristics
are a backstop, not a universal list. Domain authors must classify unfamiliar
sensitive fields conservatively.

Output columns follow policy order with `record_id` first; dropped columns never
appear. Source keys must be non-empty and unique, and remain exact strings in the
map. Source keys with spreadsheet-formula prefixes or control characters fail
before export so the resulting map remains restorable. Bin labels are limited to
64 characters. There is no `generalise` or `redact` in either version. To add an action or schema option,
follow `.github/skills/policy-schema/SKILL.md`, update examples and migration
behaviour and add rejection tests first.
