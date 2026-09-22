# Verification

Verified on macOS ARM64 using the active pyenv Python 3.12.13.

## Executed checks

- `.venv/bin/python -m pytest`: **141 passed**.
- `ruff check .` and `ruff format --check .`: passed.
- `python -m pip check`: no broken requirements.
- `.venv/bin/python -m build`: built a source distribution and wheel with isolated
  Hatchling 1.32.4.
- Imported the package directly from the built wheel and exercised CLI help and
  synthetic inspection; inspected archive contents. The wheel includes only the
  package and metadata; the source archive contains only the synthetic example Excel workbook.
- Validated all five `.github/skills/*/SKILL.md` files with the skill-creator validator.

The test environment resolved cryptography 50.0.1, PyYAML 6.0.3, Typer 0.27.2,
openpyxl 3.1.5,
pytest 9.1.1 and Ruff 0.16.8. Build isolation used Hatchling 1.32.4. The project uses
bounded dependency ranges, not a fully locked deployment environment.

## Behaviour covered

Synthetic source → policy → candidate → approved Excel workbook plus encrypted map → exact
restoration, including shuffled returned rows and leading-zero source keys. Tests
cover explicit worksheet selection in multi-sheet workbooks. Tests
exercise real Fernet/Argon2id encryption, fresh IDs/salts, incorrect credentials,
tampering/truncation, minimal map contents and source-value absence in output/logs.
A round trip runs with Python socket creation blocked. A separate real POSIX
pseudo-terminal test performs both secret prompts and confirms no passphrase echo.

Negative cases cover unknown/missing schemas, duplicate headings, malformed
Excel workbooks, input byte/field bounds, FIFO rejection, duplicate/aliased/unsafe YAML,
unknown policy keys/actions/classifications, version 1 compatibility, invalid
category domains, invalid or overlapping/gapped bins, numeric boundaries,
non-finite/out-of-range values, exact-number precision and normalisation, fresh
per-export category codes and rejected unapproved source categories,
duplicate/blank/unsafe source keys, direct/free-text retention, small joint groups,
invalid/duplicate/missing/unmatched returned IDs, malformed map structures, result
allowlists, identity-column collisions, formulas and control characters.

Storage and CLI tests cover default map location, repository/symlink path rejection,
map/export separation, POSIX permission checks, no-clobber writes, missing approval,
declined export, failed-validation non-publication, expanded-output size rejection,
missing restore authorisation, hidden-input fallback refusal and export-publication
failure retaining an encrypted map. Passphrases in fixtures are synthetic test
strings only; they must never be reused operationally.
The desktop controller, returned-heading review and policy authoring are tested without a
display. This execution environment
could not open a Tk window, so visual layout and interaction remain unverified.

## Not established

No independent security/cryptographic audit, formal anonymity proof, legal assessment,
dependency vulnerability audit, production dataset validation, external AI-service
suitability review or Windows ACL implementation was performed. Linux behaviour,
other Python/dependency versions, sustained large-data workloads, hostile filesystem
races, abrupt power loss, network/cloud-sync filesystems and backup recovery remain
unverified. Socket-blocked tests are evidence for the exercised paths, not an OS-level
network sandbox. No real student or university data was used.
