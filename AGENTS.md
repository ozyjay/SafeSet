# SafeSet agent instructions

SafeSet is a local data-minimisation and controlled pseudonymisation tool for
student-allocation analysis. It does not establish anonymity or legal compliance.
Use Australian English and the active pyenv `python3` (Python 3.12+).

## Safety invariants

1. **LOCAL BY DEFAULT:** ingestion, sanitisation, validation and restoration need
   no network. Do not add networking without an explicit architectural decision.
2. **DATA MINIMISATION:** retain only attributes required for the intended analysis.
3. **EXPLICIT ALLOWLISTING:** reject unexpected and unclassified fields.
4. **FAIL CLOSED:** failed mandatory validation blocks export; no override exists.
5. **NO REAL DATA IN TESTS:** use visibly synthetic fixtures, never reconstructed records.
6. **NO SENSITIVE LOGGING:** never print cell values, credentials or exception payloads
   that may contain data. Treat column headings and filenames as potentially sensitive.
7. **MAPPING SEPARATION:** encrypted maps are especially sensitive; keep them outside
   repositories and export directories. Do not automatically decrypt or create them.
8. **RANDOM PSEUDONYMS:** use cryptographic randomness, never hashes of known identifiers.
9. **ROUND-TRIP INTEGRITY:** restoration must detect malformed, duplicate, missing and
   unknown IDs and must never guess identities.
10. **NO CLAIM OF ANONYMITY:** passing checks only reduces some disclosure risks.
11. **USER REVIEW BEFORE EXPORT:** show the validation summary before explicit approval.
12. **NEVER WEAKEN SAFETY TESTS MERELY TO MAKE A BUILD PASS.**

Never commit source datasets, real university/student data, credentials, keys,
identity maps (even encrypted), restored outputs or operational exports. Gitignore
is a backstop, not an access-control system. Never upload operational input to an
agent or external service to debug it.

## Development

`docs/architecture.md` and `docs/threat-model.md` are authoritative architecture and
security decisions; `docs/data-safety-model.md` defines disclosure checks and their
limits; `docs/policy-format.md` defines the supported schema. Update these when
behaviour changes. Review generated code against the threat model. Keep domain
logic independent of CLI presentation. Transformations must be deterministic and
testable except random IDs and encryption salts. Prefer small, reviewable changes.

Run `.venv/bin/python -m pytest` and `.venv/bin/ruff check .` after relevant changes.
Reusable instructions are in `.github/skills/*/SKILL.md`; Codex agents can read
them directly, while compatible VS Code agents can discover the skill folders.
Select privacy-review, policy-schema, cli-command, safety-tests or release-review
as appropriate. Do not infer permission to publish, upload or contact services.
