# Architecture and decisions

## Standalone macOS desktop

The macOS 14+ Apple Silicon app uses SwiftUI for presentation and packages the
same Python domain modules as a one-directory executable helper. A bounded,
versioned JSON-line protocol runs solely over a child process's stdin/stdout.
The app launches the helper from its own bundle; it opens no port or server.
Requests contain local paths, explicit field decisions and transient passphrases.
Responses contain only aggregate inspection, local category values after an
explicit request, fixed error codes and review metadata. Source rows, maps,
bundle payloads and passphrases never enter protocol responses or logs.

The helper stores one pending review in memory under a random opaque token. A new
operation invalidates that review; approval consumes the token before publication.
Protection and reconstruction still recheck their inputs and use the existing
no-clobber storage boundary. The GUI controls navigation, not safety decisions.
The Tk interface has been removed; Python CLI commands remain available.

## Protected working-copy round trip (bundle version 2)

The primary workflow is source workbook → validated protected working copy and
separate encrypted restoration bundle → user analysis → new reconstructed workbook.
The original source remains authoritative for every source field, including fields
omitted from the protected copy. The modified copy is untrusted. Reconstruction
imports only individually approved new result columns; changes to any source-derived
protected field, including coded categories, are blocked. Editable source-derived
fields are deferred until a separate, explicit policy and review model exists.

The version 2 bundle is a distinct authenticated envelope. Its encrypted payload
holds an export identifier, canonical source-table SHA-256 binding, selected source
key heading, exact random ID-to-key map, source/protected schemas, strict policy
rules and observed reversible category codebooks. It holds no source rows or
dropped identifier values other than the selected key. The original source must
be supplied for reconstruction and its selected table must match the binding
exactly. Bundle version 1 identity maps remain readable only by the legacy
result-join path; reconstruction rejects them without reinterpretation.

`bundle` owns schema validation and encryption. `reconstruction` verifies source,
bundle and returned copy, then produces a new string table. `desktop_flow`
prepares aggregate reviews and enforces approval and no-clobber publication.
Source, protected copy, private bundle and reconstructed output cross separate
trust boundaries. The bundle stays outside export directories and repositories;
the reconstructed output is sensitive plaintext and never overwrites the source.
The export and restore operations need no runtime network access.

## Relational workbook round trip (bundle version 3)

The relational workflow protects an explicitly selected set of worksheets without
flattening their schemas. Each worksheet has its own strict version 3 policy and
exact source-table binding. The single `pseudonymise` field selected in every
worksheet is declared to belong to one shared entity domain: equal source-key text
therefore receives the same fresh random `entity_id` throughout the workbook.
SafeSet never infers this relationship from similar headings. Each source row also
receives a globally unique random `record_id`, so result restoration remains
unambiguous when an entity occurs in several worksheets or several rows.

The protected workbook preserves selected worksheet names and contains both IDs.
The encrypted version 3 bundle contains one `entity_id`-to-source-key map, per-sheet
`record_id`-to-source-row-index maps, exact per-sheet schemas, policies, codebooks
and source digests. It also authenticates the explicitly confirmed list of shared
obfuscation fields. A field is eligible only when its literal heading is present
with the `code` action in at least two selected worksheets. Equal source labels in
a confirmed field receive the same fresh random code across those worksheets;
same-named fields that are not confirmed retain independent codebooks. This is
workflow configuration rather than an inferred schema relationship. It contains
no dropped fields or whole source rows. All sheets
are reviewed and published as one release; a failure in any sheet or in linked
validation blocks the workbook. Publication writes the authenticated private bundle
before the protected workbook, so a failure may leave an orphan bundle but never a
protected workbook without its bundle.

Reconstruction requires the exact original and returned worksheet set. It verifies
every record ID, entity ID, protected value, source row position and workbook
binding before importing explicitly approved new result columns per sheet. The
result is a new multi-sheet sensitive workbook. Version 2 and version 3 bundle
envelopes are not reinterpreted or migrated implicitly.

Shared entity IDs deliberately reveal equality, cross-sheet participation and
frequency patterns. Validation therefore reports per-sheet marginal and joint
groups plus linked entity fingerprints formed from every released source-derived
attribute and worksheet participation pattern. Confirmed shared obfuscation
codebooks additionally reveal cross-sheet category equality and frequency and are
called out in the release review.

## Validation profiles

`strict` remains the default. Small retained-value groups, small per-sheet joint
classes and small linked entity classes are mandatory failures.

`controlled_pseudonymisation` is an explicit release profile. It retains all
structural, schema, domain, unsafe-text, identifier and integrity failures as
mandatory blockers, but reports the three small-group findings as prominent
warnings for explicit human review. It is not a validation bypass and does not
claim anonymity. The selected profile is authenticated in a version 3 bundle;
single-sheet approval revalidates with the reviewed profile immediately before
publication. Changing profiles invalidates the desktop review.

## Existing version 1 map path and shared foundations

The CLI and SwiftUI desktop helper delegate to typed Python domain modules.
No domain module uses a network client, telemetry or remote classification.
Installation may download dependencies; runtime does not need network access.

`ingestion` reads selected bounded `.xlsx` worksheets into one string table. `policy`
loads a strict YAML schema.
`classification` supplies advisory local heuristics. `transform` creates an
in-memory candidate and minimal mapping. `validation` evaluates export conditions.
`mapping` encrypts/decrypts the identity map. `storage` enforces destination
separation and exclusive file publication. `restoration` performs exact joins.
`workflow` coordinates approved export; `cli` handles terminal review and secret
prompts. `desktop_flow` coordinates the same domain operations for `desktop`, which
uses native file pickers and masked passphrase entries. A prepared candidate remains
in memory until its validation summary is reviewed and export is approved. Editing
an input field invalidates the review. The publication boundary revalidates and
checks destinations again.
`policy_authoring` builds strict version 3 policies from explicit desktop choices,
checks the source heading set again, and publishes a private, no-clobber YAML file
outside repositories. Advisory classification hints never select an action. Distinct
category values appear in the desktop only after a separate local review action;
the user must then approve the allowlist. An existing strict policy can prefill the
form, but revisions publish to a new file. Saving a policy does not approve export.
The desktop restoration flow reads returned headings and checks ID format before
asking for the passphrase. The user explicitly approves every non-ID returned
column and every added analysis worksheet; restoration still requires exact schema
and mapping coverage for the original protected worksheets. In relational restore,
the user may exclude added analysis worksheets before validation, but cannot omit
any worksheet authenticated by the bundle. Included added worksheets are
validated as bounded tables, rechecked after review and copied as static cell text
without formatting, drawings or pseudonymous-ID translation. Formula cells are
accepted only there and only through a saved scalar result; formulas are never
calculated or copied. Its output picker selects a new filename
rather than an existing file.
Optional coded-label restoration reads the original source workbook and policy
locally after separate authorisation. It requires exact source-key coverage and
matching coded-category groupings, replaces only approved `code` result columns,
and never rejoins dropped fields. No codebook or source snapshot is added to the map.
`diagnostics` writes allowlisted stage and reason codes to a private local log
outside repositories. It never accepts free-form event text. On POSIX, the log
directory requires owner-only mode 0700 and the file mode 0600; symlinks and
hard-linked log files are rejected. Logging is best effort and does not change
validation, approval or publication outcomes. The log is truncated at 1 MiB.

Inputs must be regular files. Excel workbook limits are 10 MiB compressed,
50 MiB uncompressed, 50,000 data rows, 128 columns and 4,096 characters per
field. A workbook may contain multiple worksheets. For a version 2 bundle, the
desktop can combine explicitly selected worksheets when their headings match in
the same order; it preserves their workbook order. A version 3 bundle processes
its explicitly linked relational set automatically. The legacy CLI path has the
same same-schema combining behaviour. Selected worksheet rows are appended in
workbook or supplied order, with the row limit applied to the combined table. Duplicate source keys
fail before export; no automatic choice is made between overlapping records. Only selected sheets enter
inspection, sanitisation or restoration. Source data formulas use only scalar
results saved in the workbook; SafeSet does not calculate formulas or verify that
saved results are current. Missing or unsupported saved results and formulas in
headings fail closed. The inspection and export review show the number of saved
formula results used, and export review warns that they may be stale. Source
Excel date/time cells are converted to ISO text for inspection and policy
review; they are counted in the review. Exact date-shaped values cannot pass the
categorical policy checks. Candidate validation and returned analysis files still
reject formula cells and returned Excel date/time cells. Links, hidden rows
or columns and merged cells in selected data ranges are rejected. Where a selected sheet
contains structured Excel Tables, only their defined ranges are ingested;
matching tables are appended in sheet position order. A declared totals row is
excluded. Titles, notes, merged cells and other content outside table ranges are
ignored and do not enter inspection or export. A range that only looks like a
table is treated as a plain worksheet, so title rows may then be read as headings.
Table header cells must match the table metadata exactly. External
workbook links are rejected. Policies are limited to 256 KiB and encrypted maps to 32 MiB.
Plain worksheets may contain filters and drawings; these do not enter the data
table. Size limits apply to populated cells, so formatting of empty cells outside
the table does not trigger a limit. Hidden rows or columns within the data range
still fail closed.
Candidate exports must fit the same 10 MiB byte limit before publication.
These bounds serve a modest local dataset workflow; this is not a streaming engine.

## Version 1 map decisions and shared safeguards

- Python 3.12+, Typer, PyYAML, cryptography, openpyxl and pytest. Workbook
  values are read without dataframe type inference; numeric cells become plain
  decimal text. Source identifiers requiring exact formatting must be stored
  as text in Excel. Exports write every cell as text.
- Strict version 1, 2 and 3 policies; unknown options, duplicate YAML keys, aliases,
  unknown classifications, malformed bounds/bins and source-schema drift are errors.
- Policy, mapping and result headings preserve literal Excel text within the
  ingestion bounds (non-empty, unique, at most 64 characters, no surrounding
  whitespace or controls). Exact matching and explicit allowlists remain required.
  This backward-compatible rule applies to all policy versions and existing maps.
- Exactly one unique, non-empty source identifier is pseudonymised to `record_id`.
  Other direct identifiers and all free text must be dropped. Map only that key,
  never names, notes or whole source rows. Rejoining dropped source fields is a
  separate local operation outside this workflow.
- Keep and code actions require explicit finite categorical `allowed_values`.
  Codes are random per distinct observed category, column and run. The category
  codebook exists only in memory and is not added to the encrypted identity map.
  Bins generate labels under the original column heading. Version 3 numeric keep
  requires bounds, has no decimal-place limit, preserves genuine blank cells, and
  preserves normalised exact numeric text. Version 2 retains its configured
  precision limit. No inferred text redaction.
- Every retained attribute participates in the joint equivalence-class check,
  including analytical attributes; no silent risk exemption via classification.
- Candidate data stays in memory until validation and explicit export approval.
  `--create-map` authorises mapping creation; `--approve-export` is an explicit
  non-interactive approval, not a validation override. Otherwise prompt after review.
- Passphrase input is interactive, hidden and unavailable as a CLI argument or
  environment variable. Argon2id derives a Fernet key; the versioned file envelope
  stores only a random salt and authenticated ciphertext. Fixed KDF parameters
  prevent input-selected resource exhaustion (64 MiB, 3 passes, 4 lanes).
- Maps default to `~/.local/share/safeset/maps/<random>.enc`, but only after
  explicit creation. Reject maps within the checkout, current Git worktree,
  source repository or export directory. Resolve symlinks before checking.
  Reject outputs in detected repositories. Never overwrite existing destinations.
- Private map directories require current-user ownership and mode 0700 on POSIX;
  newly written artefacts use mode 0600. Files are staged in destination directories,
  flushed and published with a no-clobber hard link. Publish encrypted map first,
  then export. A failure/crash between publications can leave an orphan encrypted
  map; it must never leave an export without its previously published map.
- Restoration requires `--authorise`, exact mapping coverage and an explicit
  `--result-column` for each returned non-ID column. It returns the selected source
  key plus approved result fields, preserving returned row order. Identity-column
  collisions, duplicate/missing/unknown IDs and spreadsheet formulas are rejected.
  Supplying the original source and policy additionally restores category labels
  only for approved coded fields; source keys must match the map exactly.

Paths are checked at use time; a hostile process with the same account can race
these checks. Filesystem transactions, secure deletion and protection from a
compromised host are out of scope. Repository detection is a guardrail, not a way
to identify every possible data-sync destination.
