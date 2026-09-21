# Policy version 1

See `examples/example-policy.yaml`. YAML mappings reject duplicate keys and aliases;
unknown keys and types fail. Top-level keys are exactly `version`, `columns` and
`min_group_size`. The version must be integer 1; minimum group size an integer >=2.
Column names are ASCII snake_case, at most 64 characters. `record_id` is reserved.
Source headings must match the policy exactly (order may differ).

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

Keep labels must be short categories. Use quoted YAML strings for numbers/booleans.
A heading detected as a direct identifier cannot be kept even if classified as an
analytical attribute. A heading detected as free text must be dropped. Heuristics
are a backstop, not a universal list. Domain authors must classify unfamiliar
sensitive fields conservatively.

Output columns follow policy order with `record_id` first; dropped columns never
appear. Source keys must be non-empty and unique, and remain exact strings in the
map. Source keys with spreadsheet-formula prefixes or control characters fail
before export so the resulting map remains restorable. Bin labels are limited to
64 characters. There is no `generalise` or `redact` in v1. To add an action or schema option,
follow `.github/skills/policy-schema/SKILL.md`, update examples and migration
behaviour and add rejection tests first.
