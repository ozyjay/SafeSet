# Verification

## Restore participant comparison — 25 September 2026

Added explicit target/reference comparison to version 4 Restore, bounded proposal
validation, local field mappings, separate addition/removal approvals and surgical
target-range replacement. No operational input, bundle or passphrase was used.

- Full Python suite: **292 passed, 24 Windows-only tests skipped**.
- New participant coverage: **27 tests passed**. Real encrypted synthetic bundles
  exercise additions plus edits, removal with local reference mapping, missing
  assignments/mappings, duplicate/unknown/existing-target IDs, extra fields/sheets,
  hidden sheets, altered reference values, invalid domains, exact original record
  coverage, stale full-file digests, explicit approvals and single-use bridge
  tokens. Writer checks cover space collisions, row compaction, numeric addition
  cells, surviving styles and byte-for-byte unchanged unrelated ZIP members.
- Swift package: **20 tests passed**, including incomplete-review, participant
  approval and configuration-change gates and explicit blank-vs-missing mappings.
- The ad-hoc signed native Mac app built successfully. A relocated packaged helper
  completed participant-addition restoration with development Python settings
  removed from its environment; responses contained no synthetic identity values
  or passphrase. Legacy/editing packaged smoke checks, strict code-signature
  verification and bundled-guide freshness checks also passed. The tested app was
  installed locally at `~/Applications/SafeSet.app`.
- Wheel built and inspected: Python modules and package metadata only, including
  both new modules. CLI help smoke passed after local wheel installation with no
  dependency downloads. The declared Hatchling build backend was installed in the
  development environment to build the wheel.
- Changed Python files pass Ruff. Whole-repository Ruff still reports the same
  **19 pre-existing document-related issues**. Tracked artefact extension checks
  found no encrypted maps, keys or operational outputs.

Privacy review found no blocking issue in the exercised paths. Identity resolution
uses the authenticated entity map, original record coverage stays mandatory, and
new values are constrained to editable domains or explicit local reference-field
choices. No networking was added; a round-trip test blocks socket creation.
Review metadata contains counts, headings and configuration, never participant
values or codebooks. Output approval rechecks full input-file digests and rebuilds
the proposal; exclusive publication preserves no-clobber behaviour.

Limits: participant changes require the bounded target layouts documented in
HOWTO.md. New mapped reference values are literal text. Formula recalculation and
range expansion were not performed; fixed summaries/charts need local review.
The reference choice and substantive correctness of assignments are human
decisions. Windows publication/UI, independent security review, signing with a
Developer ID and notarisation were not tested or enabled by this change.

## macOS editable workbook pass — 25 September 2026

Implemented version 4 editable-field bundles, per-sheet reference permissions,
aggregate change review and original-package restoration. Verification used
synthetic fixtures only; no operational workbooks or private bundles were used.

- Python suite: **265 passed, 24 Windows-only tests skipped**.
- New editable-workbook coverage: **31 tests passed**, including real encrypted
  bundle round trips, shared-code reassignment, reordered returned rows, exact
  untouched ZIP-member preservation, charts/styles/formulas, missing/duplicate/
  unknown IDs, reference edits, extra fields/sheets, domain violations, stale source
  and returned inputs, source-package changes after protection review, explicit
  change approvals, numeric precision and old-bundle immutability.
- Swift package: **18 tests passed**, including per-sheet permission scoping and
  the explicit changed-field approval gate.
- Native app build and strict code-signature verification passed. The relocated
  standalone helper passed both the original reconstruction and new editable-field
  round trips with development Python settings removed from its environment.
- Ruff passes for all changed Python files. Repository-wide Ruff reports **19
  pre-existing issues** in `document_bundle.py`, `document_cli.py` and
  `test_document.py`; these are outside this workbook change.

Privacy review found no new blocking issue in the exercised flow. The encrypted
bundle stores permissions and digests alongside existing minimal identity/code
maps; protocol reviews expose headings/counts and prompt bounds, not source rows
or codebooks. Tests block network use during editing restoration and assert that
source identifiers and passphrases do not appear in protocol responses. Publication
rechecks the original package and returned tables against the reviewed proposal.

Remaining limitations: change counts do not establish analytical correctness;
formula recalculation is requested from Excel and was not executed by SafeSet in
these tests. Selected reference tables still require ordinary protection policies
and a source key in the declared entity domain. Original unselected sheets remain
local and are copied during restoration. Native Windows editable-workbook UI and
publication were not enabled or tested in this pass.

## Current Windows development pass — 25 September 2026

Baseline: clean checked-out `main`, commit `f5fdd05` (merged document/Windows
foundation). Inspected repository instructions, architecture, threat/safety models,
document flow/bundle/bridge code and the WinUI sources before code changes.
The historical macOS totals below are not current Windows results.

Environment: Windows AMD64 build 26200, local NTFS temporary storage, PowerShell
7.6.6, .NET SDK 10.0.303. No active pyenv executable or existing Windows virtual
environment was available. The `python3` command was an inaccessible Store alias.
Created `.venv` using the installed CPython 3.12.10 `python.exe`; no runtime or
test dependencies were installed. Offline installation from the existing uv cache
failed because required packages, including cryptography, were unavailable.
The user explicitly required this pass to remain offline.

Baseline checks attempted:

- `.venv/Scripts/python.exe -m pytest`: blocked, no pytest module.
- `.venv/Scripts/python.exe -m ruff check .`: blocked, no Ruff module.
- `scripts/smoke-windows-ux.ps1`: failed at dependency restore. NuGet packages
  were unavailable; no successful frontend build is claimed for this pass.

Post-change checks:

- `.venv/Scripts/python.exe -m unittest discover -s tests/windows -v`, with
  `PYTHONPATH=./src`: **24 tests, 22 passed, 2 skipped**. Real Windows API and
  independent PowerShell ACL checks exercised private directory/file creation,
  protected DACLs, explicit Everyone access rejection, inherited ACE rejection,
  null DACL rejection, unsupported deny ACE rejection, optional SYSTEM/Admin
  access, file symlinks, directory junctions, multiple hard links, reserved/device/
  UNC/stream paths, private export staging, no-clobber, repository exclusion,
  map/export separation and fixed error messages. Failure-injection tests cover
  native API errors; they do not substitute for the real ACL checks.
- Skipped: encrypted DOCX round trip (missing cryptography/openpyxl/PyYAML), and
  changing ownership to Administrators (required privilege unavailable).
- `scripts/smoke-windows-ux.ps1 -NoRestore`: blocked by the previous unresolved
  NuGet restore; failed with five dependency errors. This added option performs
  no restore and does not work around missing dependencies.
- Python `compileall` for `src` and `tests/windows`, PowerShell parsing of the
  changed smoke script, and `git diff --check`: passed. These checks do not
  substitute for Ruff or the full regression suite.

The WinUI shell remains a preview with no publication path. No backend controller,
DOCX UI approval workflow or Windows helper packaging is claimed complete. No
operational data was used. Full Python regression/lint, encrypted document/bundle
behaviour on Windows, a privileged wrong-owner test, a second-user access test,
unsupported-volume hardware tests, packaged app testing and POSIX regressions
remain unverified. Some existing fixtures assume POSIX modes and must be reviewed
when running the full suite on Windows; this pass did not weaken or skip them.

Supply the declared dependencies locally to resume the encrypted/full-suite
checks before enabling the native DOCX workflow. Historical results below remain
historical evidence only.

## Historical macOS verification (not rerun in this pass)

The protected working-copy suite in `tests/test_reconstruction.py` uses only
synthetic records. It exercises version 2 bundle encryption and authentication,
source binding, full-source reconstruction, new-field approval, malformed,
missing, duplicate and unknown IDs, altered protected values, schema collisions,
legacy envelope rejection and no-clobber output publication. The original CLI
and version 1 map tests remain in place.

The earlier macOS change was checked on macOS ARM64 using the active pyenv Python
3.12.13. The detailed package and dependency checks below describe the earlier
baseline unless repeated in this iteration.

### Historical executed checks

- `.venv/bin/python -m pytest`: **218 passed**.
- `ruff check .`: passed.
- `swift test --disable-sandbox --package-path macos/SafeSetMac`: **12 passed**,
  including consolidated cross-sheet field decisions, exact per-sheet categorical
  allowlists, and remembered, forgotten and stale private-bundle path cases.
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

### Historical behaviour covered

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
non-finite/out-of-range values, exact-number blank preservation, version 2 precision
compatibility, version 3 unlimited decimal places and normalisation, fresh
per-export category codes and rejected unapproved source categories,
duplicate/blank/unsafe source keys, direct/free-text retention, small joint groups,
invalid/duplicate/missing/unmatched returned IDs, malformed map structures, result
allowlists, identity-column collisions, formulas and control characters. Restoration
tests also cover approved added analysis worksheets, missing worksheet approval,
blank analysis cells and unsafe worksheet content.

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

### Historical limitations

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
