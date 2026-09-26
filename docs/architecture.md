# Architecture and decisions

## Windows private-storage implementation contract

The Windows boundary uses the standard-library `ctypes` bindings to local Win32
security APIs; it adds no dependency or subprocess ACL parser. New private
directories and staged files receive a protected DACL at creation, with full
control only for the current process user. Existing objects must be owned by
that user, have a protected DACL and contain only explicit full-control allow
ACEs for that user, optionally LocalSystem and built-in Administrators. Unknown
ACE types, inherited ACEs, null DACLs and additional principals are rejected.
Existing permissions are never silently repaired. The validation policy is
deliberately narrower than all possible secure Windows ACL configurations.

Only local fixed NTFS volumes are supported initially. Device/UNC paths,
alternate streams, reparse points in any existing path component and multiply
linked private files are rejected. New staged files are private before any bytes
are written, flushed and published without replacing an existing destination.
Repository rejection and separate bundle/export directories remain mandatory.
This contract must pass real Windows integration checks before the desktop
publication gate is removed.

## Standalone macOS desktop

The macOS 14+ Apple Silicon app uses SwiftUI for presentation and packages the
same Python domain modules as a one-directory executable helper. A bounded,
versioned JSON-line protocol runs solely over a child process's stdin/stdout.
The app launches the helper from its own bundle; it opens no port or server.
Requests contain local paths, explicit field decisions and transient passphrases.
Responses contain only aggregate inspection, local category values after an
explicit request, fixed error codes and review metadata. Source rows, maps,
bundle payloads and passphrases never enter protocol responses or logs.

For restoration convenience, the SwiftUI process stores the path of the
most recently created or selected encrypted private bundle and the most recently
created workbook's relational-mode flag in its local app preferences. It prefills
the path only while it still names an existing `.enc`
file, removes stale preferences and provides an explicit forget control. The
passphrase and decrypted bundle content are never stored in preferences, and the
bundle is not opened until the user requests validation.

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
fields use the separate version 4 workflow described below.
Returned protected columns may appear in any order, with new result columns
interspersed. Restoration matches exact, unique headings to the authenticated
protected schema, checks every protected value by record ID and requires explicit
approval for every new heading. Missing or renamed protected headings still block
restoration. When version 2 restoration combines returned worksheets, their
headings must match as a set, even if their order differs.

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

## Editable workbook round trip (bundle version 4)

The native Mac protection flow defaults to editing selected existing fields.
The native Debug build has a synthetic-fixture convenience path: an exact
allowlisted workbook digest selects a known development passphrase for workbook
protection and restoration. Release builds compile out this path; other source
workbooks use the normal passphrase flow. This does not alter the encrypted
bundle format, validation or approval rules. The Debug app has a distinct bundle
identifier and is launched from the build directory, separate from the installed
Release app.
Per-sheet `editable_fields` lists explicitly authorise `keep`, `code` and
`keep_numeric` fields; an empty list makes a selected sheet reference only.
Identifiers, dropped fields, bins, formula cells and date cells cannot be editable.
Every selected sheet still needs its normal protection policy and declared source
key in the shared entity domain. Supporting sheets without that structure can
remain local; selecting a reference role does not bypass disclosure checks.

The `SAFESET4` envelope authenticates the version 3 relational payload plus exact
editable-field lists and a SHA-256 binding of the entire original file. Versions
2 and 3 remain immutable and are never upgraded implicitly. Version 4 requires a
new protection run. Workflow permissions are separate from policy YAML versions.
Protected output remains minimal static tables; original formatting, local-only
worksheets and original formulas are never sent to the analysis recipient.

Returned workbooks must retain exact row IDs, entity links, protected headings
and reference values. Row and column reordering is allowed. Standard editing accepts
no extra sheets or columns; the explicit participant comparison below accepts one
bounded proposal sheet. Edited categories must be observed values;
edited codes must resolve in their authenticated codebook, or the union of an
explicitly shared same-field codebook. Numeric edits obey policy bounds and blank
semantics. The engine reports changed-cell counts per field without exposing row
values, and requires explicit approval of every changed field.

`workbook_editing` maps source rows to exact worksheet coordinates through the
bounded ingestion reader, including multiple structured table regions. Restoration
uses the original package as its base, applying only approved changes in source
row order. Unmodified ZIP members, including reference/local-only worksheet XML,
styles, drawings and charts, are copied byte-for-byte. Changed worksheet XML keeps
its remaining cells and layout. Original formulas are retained and workbook
calculation flags request recalculation in Excel; SafeSet does not calculate them.
Existing numeric cells stay numeric; values exceeding Excel's 15 significant-digit
precision are rejected before review. Numeric fields stored as text stay text.
Digitally signed packages requiring edits and ambiguous XML layouts fail closed.

The complete proposed workbook is built in memory before review, then rebuilt
and compared at approval after rechecking the full original file and returned
tables. Publication remains local and no-clobber. No source rows or workbook bytes
are added to the encrypted bundle or protocol responses. The engine-generated
prompt lists only authorised headings, domain instructions and approved numeric bounds. New
desktop protocol options are `editable_fields` on relational protection and
`approved_changes` on relational approval; the review returns `changes` as
per-sheet/per-field counts and `analysis_prompt` as copyable instructions. Existing
requests without editing permissions retain their version 3 behaviour.

The macOS prompt view can append an operator-written task using exact worksheet
and field names. This text stays in desktop UI state and is neither a bundle
permission nor a protocol input. The UI asks the operator not to include direct
identifiers; SafeSet cannot verify arbitrary text before the operator copies it.
The copied prompt states that the task cannot authorise new codes, categories or
workbook structure.

### Result-only workbook restoration

A separate Restore path accepts a new workbook of result sheets for a version 3
or 4 related-sheet bundle. The returned workbook need not contain any protected
source worksheet. A participant result row carries a known `entity_id`; an
optional `record_id` must belong to that entity. Summary sheets contain no ID
control columns. The operator selects a bound source sheet, exact source fields,
join key and per-sheet duplicate-entity rule. Missing or ambiguous joins block
publication. The output contains only the result sheets, with control IDs removed
and selected original fields joined locally.

Known category codes are decoded by authenticated field/codebook association.
Novel short result values, including new team labels, are counted and approved as
new output categories; they do not alter source codebooks. Unknown UUID-shaped
codes and ambiguous codebook associations fail. Every result sheet, result field,
new-category field and source join requires review. The helper rereads both
workbooks and rebuilds the proposal at approval before no-clobber publication.
The copied result-workbook prompt is a short output contract; allocation rules
may be worked out in ChatGPT and are not enforced by SafeSet.

### Participant comparison during Restore

Version 4 Restore can explicitly compare one editable target sheet with a distinct
reference-only sheet in the same authenticated bundle. Each must contain at most
one record per entity. The operator selects additions and/or removals locally;
removals default off. All original returned records must still occur exactly once,
including departing participants. Missing original records never imply removal.

An explicitly named extra proposal worksheet may contain only `entity_id` and the
target's editable fields. Proposal IDs must be unique members of the authenticated
reference-minus-target set. Existing entity IDs, unknown IDs, extra fields and
invalid categories/codes/numbers fail closed. Missing assignments produce an
incomplete review with counts and a copyable prompt; publication stays disabled.
No assignment is inferred. All other extra or hidden returned sheets are rejected.

For additions, the source key comes from the encrypted entity mapping. Every other
noneditable target field needs an explicit local source sheet and column selection
or Leave blank decision. Source sheets must be reference-only sheets in the same
authenticated bundle, with at most one row per entity. A selected source must
contain every incoming entity and a value for the selected field; missing matches
or values block publication. These original
source values stay local. Surviving rows
retain source order and original cell types/styles; additions follow reference
source order. Added mapped fields are literal text, and editable numeric additions
are numeric cells subject to Excel precision checks. Review covers changed fields,
addition count, removal count and local field sources. Separate approval is required
for each nonzero participant change type as well as every changed field.

Structural updates support one plain rectangular range or one Excel table without
totals. They replace cells within that target rectangle, resize its table/filter,
and require empty space for expansion. Physical worksheet rows are not deleted.
Formulas, merged/hidden data, comments, hyperlinks, worksheet data validation and
conditional formatting block structural changes. Other package entries remain
byte-for-byte unchanged except calculation flags. Fixed formula/chart ranges and
static summaries are not expanded; the user must review them locally in Excel.

`prepare_participants` takes restoration paths, passphrase and `config`;
`update_participants` consumes a review token and new config without another
passphrase. Config contains `target_sheet`, `reference_sheet`, `additions_sheet`,
boolean `include_additions` / `include_removals`, and `column_sources` mapping target
headings to `{sheet, column}` or null. Legacy reference-column strings remain
accepted for existing clients. Unselected mappings remain missing, not
implicitly blank. `approve_participants` consumes the latest token with exact
`approved_changes` and boolean `approve_additions` / `approve_removals`. Incomplete
reviews cannot publish. Any token operation consumes the previous token. Full
original and returned file digests are rechecked; the output is rebuilt and
compared to the reviewed proposal before exclusive publication. Bundle contents
remain in helper memory; protocol responses contain counts, headings and config,
never participant values or codebooks. Legacy restoration remains unchanged.

## Relational workbook round trip (bundle version 3)

The relational workflow protects an explicitly selected set of worksheets without
flattening their schemas. Each worksheet has its own strict version 3 policy and
exact source-table binding. The single `pseudonymise` field selected in every
worksheet is declared to belong to one shared entity domain: equal source-key text
therefore receives the same fresh random `entity_id` throughout the workbook.
SafeSet never infers this relationship from similar headings. Each source row also
receives a globally unique random `record_id`, so result restoration remains
unambiguous when an entity occurs in several worksheets or several rows.

Worksheet selection determines the protected workbook's contents: selected worksheets are protected and
included, while unselected worksheets are excluded rather than copied through.
No source worksheet is copied unchanged into a protected export. Version 4 adds
reference roles and preserves local original worksheets during restoration only.

The protected workbook preserves selected worksheet names and contains both IDs.
The desktop inspects every selected worksheet and consolidates fields by exact
literal heading for authoring. One visible decision is copied into each matching
per-sheet policy, while the interface displays the affected worksheet names.
Categorical review presents the union of labels to the operator but retains each
worksheet's exact observed allowlist in its own policy. Sheet-specific headings
remain separate. Consolidation does not infer that same-named fields have the same
semantics; that judgement remains explicit operator responsibility.
The desktop initially filters the editor to fields whose decisions or required
category/numeric settings remain incomplete. Operators can show all fields to
revisit decisions. Its bulk Remove action applies only to headings that have no
action in every selected worksheet; any configured decision is left alone. Each
field card also has an X that sets Remove directly. Removed cards are shown
inactive in the all-fields view and can be restored to an undecided state there.
These controls change authoring convenience, while per-sheet policies and
validation still require explicit decisions for every source field.
Remove and pseudonymise do not expose raw classification pickers: an unclassified
removed field serialises as `unknown`, and the selected linking field serialises
as `direct_identifier`. Retained and transformed fields use plain-language choices
mapped to `analytical_attribute` or `quasi_identifier`; the uncertain choice is
an unresolved, blocking authoring state. Local heuristics only explain a suggestion
and never set an action or grant permission.
The encrypted version 3 bundle contains one `entity_id`-to-source-key map, per-sheet
`record_id`-to-source-row-index maps, exact per-sheet schemas, policies, codebooks
and source digests. It also authenticates the explicitly confirmed list of shared
obfuscation fields. A field is eligible only when its literal heading is present
with the `code` action in at least two selected worksheets. Equal source labels in
a confirmed field receive the same fresh random code across those worksheets;
same-named fields that are not confirmed retain independent codebooks. This is
workflow configuration rather than an inferred schema relationship. It contains
no dropped fields or whole source rows. All sheets
are reviewed and exported as one protected workbook; a failure in any sheet or in linked
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
groups plus linked entity fingerprints formed from every exported source-derived
attribute and worksheet participation pattern. Confirmed shared obfuscation
codebooks additionally reveal cross-sheet category equality and frequency and are
called out in the protection review.

## Validation profiles

`strict` remains the default. Small retained-value groups, small per-sheet joint
classes and small linked entity classes are mandatory failures.

`controlled_pseudonymisation` is an explicit validation profile. It retains all
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
The macOS frontend keeps the local JSON-line backend bridge, observable app
model and SwiftUI views in separate Swift source files. The Xcode target lists
each file explicitly, while the Swift package includes the `Sources` directory.

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
the authenticated bundle supplies the mandatory worksheet set automatically; the
desktop sends no worksheet selection. Every other visible worksheet is discovered
as added analysis and shown separately for approval, while any hidden returned
worksheet blocks review. Included added worksheets are
validated as bounded tables, rechecked after review and copied as static cell text
without formatting, drawings or pseudonymous-ID translation. Formula cells are
accepted only there and only through a saved scalar result; formulas are never
calculated or copied. Its output picker selects a new filename
rather than an existing file.
After a protected workbook is created, the desktop shows the static
returning-analysis prompt in a copyable sheet and keeps a reminder on the home
view for that session. The same prompt remains available from restoration; its
copy action places only those fixed instructions on the clipboard.
The prompt tells recipients to use one rectangular table per added analysis sheet,
without merged titles or spacer rows, and to keep workbook results as short
categories. Longer narrative findings belong in the recipient's separate reply,
because added analysis cells still pass the shared engine's unsafe-text checks.
Optional coded-label restoration reads the original source workbook and policy
locally after separate authorisation. It requires exact source-key coverage and
matching coded-category groupings, replaces only approved `code` result columns,
and never rejoins dropped fields. No codebook or source snapshot is added to the map.
`diagnostics` writes allowlisted stage and reason codes to a private local log
outside repositories. It never accepts free-form event text. On POSIX, the log
directory requires owner-only mode 0700 and the file mode 0600; symlinks and
hard-linked log files are rejected. Logging is best effort and does not change
validation, approval or publication outcomes. The log is truncated at 1 MiB.
The desktop bridge also maps exact, fixed restoration failures to value-free
error codes for local user guidance. Unknown failures remain generic; exception
text, headings, cell values and paths do not cross this error boundary.
The separate, user-invoked source-text locator reuses bounded Excel ingestion,
authenticates the private bundle and verifies the source binding before returning
only a count and at most 20 worksheet names and cell coordinates to the local UI.
It does not return cell values or change export and restoration decisions.

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
- During bundle reconstruction, the bound original source supplies dropped fields
  to the local restored workbook. Formula-like source text is written as literal
  Excel text; source control characters still block restoration.
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


## Cross-platform desktop contract

SafeSet now treats the desktop bridge as a shared internal contract rather than a macOS-specific implementation detail. The Python helper remains the authority for inspection, validation, review-token lifecycle, protection, restoration and publication. Native shells may differ in presentation:

- macOS: SwiftUI;
- Windows: WinUI 3 / Windows App SDK.

Both shells communicate with the helper over the same bounded JSON-line stdin/stdout protocol. The protocol returns aggregate review metadata and fixed safety codes; sensitive source values and private mapping contents do not cross back to the UI. Platform shells must not reimplement safety decisions.

Windows support has a separate security release gate. Private-bundle storage
dispatches to POSIX ownership/mode checks or the restricted Win32 NTFS ACL
implementation described above, and rejects other platforms. The native Windows
desktop remains in preview mode: encrypted round-trip and full safety-suite
verification are still blocked by unavailable offline dependencies. Storage tests
alone do not enable the UI or establish release readiness.

## Protected DOCX round trip (document bundle version 1)

The document workflow is source DOCX → protected DOCX plus encrypted private document bundle → external work → returned protected DOCX → new locally restored DOCX.

The DOCX reader is bounded by compressed size, unpacked size, part count and per-part size. It rejects unsafe archive paths and active macro payloads. Protection operates on Word body, headers, footers, footnotes and endnotes plus relationship attributes. It automatically recognises email and ORCID shapes and accepts explicit operator-provided identities.

Protection deliberately strips common authoring metadata and custom properties. Comments are removable as a protection action. Tracked changes, hidden text, embedded objects and identity strings split across formatted text runs fail closed in this first iteration.

Each protected value receives a fresh document-scoped random token. The encrypted document bundle stores the original value, token, kind, occurrence count and source/protected digests; it does not store the whole document. Restoration requires every expected token occurrence to remain present and rejects any returned package that already contains an original protected value. It then creates a new DOCX with the approved identities restored. Word comments and stripped authoring metadata are not reintroduced.
