# Verification

The protected working-copy suite in `tests/test_reconstruction.py` uses only
synthetic records. It exercises version 2 bundle encryption and authentication,
source binding, full-source reconstruction, new-field approval, malformed,
missing, duplicate and unknown IDs, altered protected values, schema collisions,
legacy envelope rejection and no-clobber output publication. The original CLI
and version 1 map tests remain in place.

The current change was checked on macOS ARM64 using the active pyenv Python
3.12.13. The detailed package and dependency checks below describe the earlier
baseline unless repeated in this iteration.

## Executed checks

- `.venv/bin/python -m pytest`: **195 passed** (including six bridge tests and
  the removed-field authoring check).
- `ruff check .`: passed.
- `swift test --disable-sandbox --package-path macos/SafeSetMac`: **3 passed**.
- Xcode Release build for Apple Silicon: passed.
- Relocated `SafeSet.app` bundled-helper synthetic protect/reconstruct smoke: passed.
- `codesign --verify --strict dist/SafeSet.app`: passed for the local ad-hoc signature.
- `dist/SafeSet-local.zip`: created. App binary declares macOS 14.0 minimum.
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
cover multiple selected worksheets, structured tables, schema mismatches and
duplicate source keys. Tests exercise real Fernet/Argon2id encryption, fresh
IDs/salts, incorrect credentials,
tampering/truncation, minimal map contents and source-value absence in output/logs.
A round trip runs with Python socket creation blocked. A separate real POSIX
pseudo-terminal test performs both secret prompts and confirms no passphrase echo.
Diagnostic tests check private log permissions, rejection of linked or
world-readable destinations, the absence of source values and paths, and fixed
reason-code coverage for ingestion errors.
Workbook tests distinguish populated size limits from distant blank formatting
and accept filters and charts on plain sheets.

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
The desktop controller, returned-heading review and policy authoring are tested
without a display. Swift protocol tests exercise approval, stale and malformed
requests, wrong credentials, mismatched sources, invalid returned IDs, unexpected
fields, no-clobber publication, redacted responses and blocked network creation.
The SwiftUI Home and Protect screens were opened on this host. A packaged helper
was copied to a separate directory and completed a synthetic protect and
reconstruct round trip with development Python removed from its environment.

## Not established

Developer ID signing, notarisation, DMG creation and a macOS 14 runtime test were
not completed. The current host's disk-image service returned a device error;
no signing credentials are installed. The deployment target is configured but
not yet verified on a macOS 14 machine.

No independent security/cryptographic audit, formal anonymity proof, legal assessment,
dependency vulnerability audit, production dataset validation, external AI-service
suitability review or Windows ACL implementation was performed. Linux behaviour,
other Python/dependency versions, sustained large-data workloads, hostile filesystem
races, abrupt power loss, network/cloud-sync filesystems and backup recovery remain
unverified. Socket-blocked tests are evidence for the exercised paths, not an OS-level
network sandbox. No real student or university data was used.
