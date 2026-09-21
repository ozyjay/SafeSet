# Architecture and decisions

The CLI and optional Tk desktop interface delegate to typed Python domain modules.
No domain module uses a network client, telemetry or remote classification.
Installation may download dependencies; runtime does not need network access.

`ingestion` reads bounded UTF-8 CSV as strings. `policy` loads a strict YAML schema.
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
`policy_authoring` builds strict version 2 policies from explicit desktop choices,
checks the source heading set again, and publishes a private, no-clobber YAML file
outside repositories. Advisory classification hints never select an action. Distinct
category values appear in the desktop only after a separate local review action;
the user must then approve the allowlist. An existing strict policy can prefill the
form, but revisions publish to a new file. Saving a policy does not approve export.
The desktop restoration flow reads returned headings and checks ID format before
asking for the passphrase. The user explicitly approves every non-ID returned
column; restoration still requires exact schema and mapping coverage. Its output
picker selects a new filename rather than an existing file.

Inputs must be regular files. CSV limits are 10 MiB, 50,000 rows, 128 columns and
4,096 characters per field. Policies are limited to 256 KiB and encrypted maps to
32 MiB. Candidate exports must fit the same CSV byte limit before publication.
These bounds serve a modest local dataset workflow; this is not a streaming engine.

## Decisions

- Python 3.12+, Typer, PyYAML, cryptography, pytest. Standard-library CSV avoids
  inferred numeric identifiers, automatic NA conversion and dataframe overhead.
- Strict version 1 and 2 policies; unknown options, duplicate YAML keys, aliases,
  unknown classifications, malformed bounds/bins and source-schema drift are errors.
- Exactly one unique, non-empty source identifier is pseudonymised to `record_id`.
  Other direct identifiers and all free text must be dropped. Map only that key,
  never names, notes or whole source rows. Rejoining other authorised source fields
  is a separate local operation outside the MVP.
- Keep and code actions require explicit finite categorical `allowed_values`.
  Codes are random per distinct observed category, column and run. The category
  codebook exists only in memory and is not added to the encrypted identity map.
  Bins generate labels under the original column heading. Version 2 numeric keep
  requires bounds and precision and preserves exact numeric text. No inferred
  text redaction.
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

Paths are checked at use time; a hostile process with the same account can race
these checks. Filesystem transactions, secure deletion and protection from a
compromised host are out of scope. Repository detection is a guardrail, not a way
to identify every possible data-sync destination.
