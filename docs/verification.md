# Verification

## Exact issue highlights in narrative review — 16 October 2026

The local text editor now displays temporary amber highlights and underlines at
detected issue locations. **Show match** selects a location for editing; **Next
match** cycles repeated matches. **Check for issues** runs the shared stateless
text checks without committing field approval. Explicit confirmation and approval
remain required, and the accepted text domain is unchanged.

The helper returns only bounded UTF-16 ranges, fixed reasons and existing response
bindings. Unicode case-folded matches map back to original characters. Native
highlights require the exact submitted UTF-16 snapshot; stale, out-of-bounds or
surrogate-splitting ranges are ignored. Editing resets confirmation and highlights;
closing the review clears temporary snapshots. No matched text, positions or
bindings enter logs.

- Python suite: **408 passed, 24 Windows-only tests skipped**.
- Swift package: **27 tests passed**, including native temporary text attributes,
  unchanged stored text, stale ranges, Unicode representation changes and clearing
  snapshots. Python regressions cover repeated matches, emoji, case-fold expansion
  and bounded feedback.
- Ruff and `git diff --check`: passed.
- Release macOS build, strict signature verification and relocated-helper smoke:
  passed. Packaged worksheet/region highlights and corrected approvals passed.
- No operational workbook was read for this change. No manual visual interaction
  was performed; native text attributes were verified in tests. Relaunch the rebuilt
  `dist/SafeSet.app`; the installed app is unchanged.

## Narrative address-verb self-match — 16 October 2026

An operator's local review warning was traced without printing identifiers: a
narrative prompt using "address" as a verb was inferred as an address field, so
its full response was treated as its own known identifier. Bounded narrative
address-verb phrases now suggest free text; genuine name/email/address headings
remain identifier fields. Local narrative approval excludes its own column from
inferred identifier discovery and rejects actual identifier headings explicitly.
Other identifier words retain precedence and categorical rules remain unchanged.

- Python suite: **405 passed, 24 Windows-only tests skipped**.
- Swift package: **26 tests passed**; Ruff and `git diff --check` passed.
- Release macOS build, strict signature verification and relocated-helper smoke:
  passed.
- Packaged synthetic address-verb narrative: local text approval and protection
  validation passed without self-matching. Synthetic policy regressions cover
  protection/restoration and preserve genuine identifier-heading rejection.
- A read-only local diagnostic of the operator's field confirmed the self-match
  was resolved. No operational paragraph or identifier was printed, added to tests,
  approved in the running app or exported. The installed app was not replaced.

## Visible text-review approval feedback — 16 October 2026

Recent local logs showed repeated `approve_text_review` rejections with the generic
`text_review_required` code. The native review sheet previously left the operator
without a visible response-specific explanation. Rejected text approvals now add
fixed reasons keyed by existing response bindings, with no matched values or
excerpts. The sheet displays those reasons inline, preserves edits and confirmations,
shows character counts and blocks duplicate submissions while busy. Unchanged
editor updates retain confirmation and feedback; actual edits reset confirmation.
The accepted text domain and all fail-closed publication checks remain unchanged.

- Python suite: **396 passed, 24 Windows-only tests skipped**.
- Swift package: **26 tests passed**, including fixed-code decoding, retained review
  state, duplicate-submission prevention and unchanged-versus-edited confirmations.
- Ruff and `git diff --check`: passed.
- Release macOS build, signature verification and relocated-helper smoke: passed.
- Packaged synthetic worksheet/region approvals returned fixed reasons for blocked
  text and succeeded after correction. Paragraphs, response bindings and passphrases
  remained absent from diagnostic logs.
- No operational paragraphs were read or changed; no manual visual UI check was
  performed. Relaunch the rebuilt `dist/SafeSet.app`; the installed app is unchanged.

## Reviewed long-form workbook text — 16 October 2026

The macOS field control now says **How to protect this field**, with **Keep short
categories unchanged** and a separate **Review and redact text** action. Narrative
review requires individual local confirmation and uses version 4 policies; older
policy semantics and category limits remain unchanged. The shared engine binds
complete reviewed text to original content, checks recognised/known worksheet
identifiers, includes narratives in disclosure grouping and keeps them immutable
in returned workbooks. Legacy map-only narrative export fails closed.

- Python suite: **386 passed, 24 Windows-only tests skipped**.
- Swift package: **25 tests passed**, including text-review gates and edit reset.
- Ruff and `git diff --check`: passed.
- Release macOS build and strict code-signature verification: passed.
- Existing relocated packaged-helper round trips and value-free logs: passed.
- Rebuilt packaged helper: synthetic local narrative review, approval, encrypted
  protection and editable-bundle restoration passed for worksheets and confirmed
  regions. Logs excluded paragraphs and passphrases.
- The synthetic version 4 YAML example parsed successfully. No operational
  paragraph was read into this agent, used as a fixture or exported for these checks.
- No manual visual UI check was completed: the native app-inspection connection
  was unavailable. The running/installed app was not replaced; use `dist/SafeSet.app`.
- Manual redaction may miss names or identifying context. Group checks and human
  approval do not establish anonymity. Windows publication remains gated.

## Extended literal workbook headings — 16 October 2026

Headings now accept surrounding whitespace, tabs/CR/LF and up to 4,096 characters,
preserving exact spelling through policy, mapping, bundle and restoration checks.
Excel writers escape literal CRs so XML newline normalisation cannot change a
heading. Desktop field approval lists accept the same length boundary.
Synthetic tests cover all three policy versions, both workbook writers,
whitespace-only/oversized/control-character rejection, exact duplicate rejection,
distinct whitespace spellings, schema drift, sensitive-heading detection and a
network-denied encrypted desktop round trip with a long multiline result heading.

- Python suite: **359 passed, 24 Windows-only tests skipped**.
- Ruff and `git diff --check`: passed.
- Release macOS build, strict signature verification and relocated helper smoke:
  passed.
- The operator-selected local workbook passed inspection with the rebuilt packaged
  helper. No source content was printed, copied into fixtures or exported.
- The installed/running app was not replaced; launch the rebuilt `dist/SafeSet.app`
  to use the updated helper. Cell-value disclosure checks are unchanged.

## Desktop diagnostic logging — 16 October 2026

The shared desktop bridge now records allowlisted operation names, fixed outcomes
and public error codes to the existing private POSIX log. Synthetic regressions
check workbook selection, known and unknown safety errors, malformed frames,
unknown commands, public-code coverage and unchanged responses when logging is
unavailable. Log assertions exclude source paths, headings, values, request IDs
and passphrases. No operational workbook was read for these checks.

- Python suite: **345 passed, 24 Windows-only tests skipped**.
- Ruff and `git diff --check`: passed.
- Release macOS app build and strict code-signature verification: passed.
- Relocated packaged helper: legacy and editable-workbook round trips passed;
  isolated diagnostic log contained workbook-selection, successful restoration
  and existing-destination rejection events without synthetic secrets.
- The packaged smoke uses a canonical temporary home path so macOS's `/var`
  alias does not trigger the existing diagnostic symlink guard.
- The installed app was not replaced. Windows diagnostic-file logging remains
  unavailable; this change does not relax the Windows publication gate.

## Confirmed regions and manuscript review — 26 September 2026

The shared engine now has a version 5 confirmed-region editable workbook path and
a version 2 document bundle with explicit figure and paragraph review. Synthetic
tests exercise two different logical tables on one worksheet, preservation of
titles and notes, overlapping and partial-table rejection, stale source binding,
split-run identity restoration, figure acknowledgement, suggested paragraph
removal and legacy document-bundle readability. The region round trip blocks
socket creation. The macOS UI and CLI expose the new review controls.

- Python suite: **331 passed, 24 Windows-only tests skipped** at the latest
  full run.
- Ruff: whole repository passed after formatting synthetic fixture XML.
- Swift package: **24 tests passed** and the macOS app sources compiled.
- Release-configuration macOS app build and strict local code-signature check
  passed. Its relocated helper completed the existing synthetic legacy and
  editable workbook smoke paths. The packaged helper also answered the new
  region-discovery and manuscript-review commands using synthetic inputs.
  Full new-path protect/restore was verified in the Python suite, not in the
  packaged smoke script.
- Source distribution and wheel built with Hatchling 1.32.4. The wheel contains
  the new region module and package metadata only; an isolated local install
  exposed the new workbook and document CLI commands. This smoke did not run
  the new workflows from the installed wheel.
- No native Windows build, encrypted Windows round trip, packaged-app smoke,
  second-user ACL check, signing or notarisation was completed here. Windows
  publication remains disabled in its preview shell. This is not a two-platform
  release verification.

## New result rows without original record IDs — 26 September 2026

Result workbook review now accepts blank `record_id` cells when a new result row
has a known `entity_id` and uses an entity join. It continues to reject invented
non-blank IDs, mismatched record/entity links and exact-record joins for blank
IDs. Synthetic regression tests cover these cases. A value-free local diagnostic
of the operator's returned workbook found 22 blank `record_id` cells and no
unknown `entity_id` values; it did not read a private bundle or print cell values.

- Python suite: **319 passed, 24 Windows-only tests skipped**.
- Swift package: **24 tests passed** with sandbox disabled for this local build.
- Changed Python files pass Ruff; the whole repository retains the 19 existing
  document-related Ruff findings.

## Result-only workbook restoration — 26 September 2026

Added a separate related-sheet Restore path that accepts new result sheets and
rows. Synthetic version 3 and 4 bundles exercise local entity and exact-record
joins, known-code decoding, new team labels, aggregate sheets and result-only
publication. The original workbook supplies only the source fields explicitly
selected for each joined result sheet.

- Python suite: **317 passed, 24 Windows-only tests skipped**. The new result
  coverage includes unknown/mismatched IDs, duplicate-entity policy, missing or
  colliding source joins, invented UUID-shaped codes, formula-like result text,
  stale original and returned workbooks, explicit field/category/join approvals,
  protocol metadata minimisation and no network access.
- Swift package: **24 tests passed**, including result prompt selection, explicit
  review gates and precise source-field configuration.
- Local macOS app build and ad-hoc signature verification passed. The packaged
  helper answered `hello` and recognised the new result-workbook command using
  synthetic missing-file paths. No operational data, private bundle or passphrase
  was used for packaged smoke checks.
- Changed Python files pass Ruff. Whole-repository Ruff still reports the same
  **19 pre-existing document-related issues**.

The result path keeps formula cells, hidden sheets, unsafe text, unknown IDs and
ambiguous joins fail closed. New short category values require review but SafeSet
cannot verify substantive allocation rules. The restored workbook is static and
does not carry source formatting or formulas. Windows desktop publication was not
enabled or tested by this change.

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
