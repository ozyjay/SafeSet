# Implementation plan

## Standalone Mac desktop

The SwiftUI interface now replaces Tk for macOS. A bundled Python helper preserves
the current domain rules and CLI. The first build targets Apple Silicon and macOS
14 or newer. The local app and ZIP are development artefacts. Developer ID
credentials, notarisation and macOS 14 runtime testing remain release gates;
Intel and Mac App Store distribution are deferred.

## Current protected-workbook iteration

The version 2 encrypted restoration bundle and source-bound reconstruction path
are implemented alongside the existing version 1 map path. The SwiftUI app
offers Home, Protect and Restore. Advanced tools retain the earlier policy
editor and selected-result join. The CLI has explicit `protect` and `reconstruct`
commands. Source-derived protected fields are immutable; approved new short
categorical result fields can be imported into a new sensitive workbook. Deferred
work includes deliberately editable source-derived fields, richer result domains,
bundle discovery across sessions and an independent security review.

## Milestone 1: bootstrap (before implementation)

Establish package layout, the twelve invariants, architecture, threat model,
policy contract, synthetic fixtures and five reusable agent skills. The current
Excel workbook reader uses openpyxl with explicit workbook bounds and preserves
text identifiers, including leading-zero strings.

## Milestone 2: smallest useful vertical slice

1. Bounded strict Excel workbook ingestion and duplicate-key-rejecting YAML policy loading.
2. Drop, categorical keep, numeric bin and one source-key pseudonymisation action.
3. Value-free local inspection; random UUIDv4 IDs; in-memory candidate and mapping.
4. Mandatory schema, value-domain, identifier-shape and equivalence-class checks.
5. Explicit approval; passphrase-encrypted separate map; exclusive file publication.
6. Authorised restoration with exact ID coverage and explicit result-column allowlist.
7. Synthetic integration and adversarial tests; package and CLI smoke checks.

## Milestone 3: hardening before operational use

Independent security review, target-platform permission checks, dependency
maintenance, realistic *synthetic* volume testing, approved policy ownership,
local storage/backup process and an incident procedure. Passing unit tests is not
a security audit. No production-readiness or anonymity claim is made.

## Deferred

Generalisation hierarchies, redaction, free-text processing, partial/cohort
restoration, map rotation/recovery, additional privacy models and large-file
streaming. Do not add an export override. Resolve any security-sensitive change
in the architecture and threat model before coding it.

The earlier inspect/policy/export/restore interface remains available under
Advanced tools for existing version 1 workflows.

## Dataset-owner choices

Which attributes are necessary? What equivalence-class threshold is appropriate?
Where are the private map directory and restored files stored and backed up?
Who may approve export and restoration? Is the intended external service suitable?
The supplied synthetic policy is illustrative, not an institutional policy.


## Current document-protection iteration

DOCX protection/restoration is being added as a second first-class artefact workflow rather than extending the spreadsheet policy model. The first vertical slice provides bounded DOCX package parsing, aggregate inspection, explicit identity terms, automatic email/ORCID protection, metadata stripping, optional comment removal, random reversible tokens, encrypted document bundles and exact-token restoration.

Tracked changes, hidden text and embedded/active content fail closed. The next
iteration added explicit local suggestions for affiliations and acknowledgements,
split-run exact-term protection and a figure inventory with operator review.
Figure pixels remain unexamined. Deferred document work includes safe tracked-change
flattening, richer Word run reconstruction and additional Office formats.

## Native Windows desktop

Windows 11 x64 is the initial Windows target. Use WinUI 3 / Windows App SDK as a native shell over the shared Python helper and JSON-line protocol. Do not port safety logic into C#.

The shared engine now implements protected NTFS ACL creation and validation using
Win32 APIs through `ctypes`, with native storage integration tests. The current
offline development pass cannot verify the encrypted document round trip or run
the full safety suite because required Python packages are unavailable. The UI
remains in preview mode. Next, supply the declared dependencies locally, run the
encrypted and full regression checks, then implement the bounded Windows backend
controller and DOCX review/approval flow. Packaging and workbook parity follow
that verified vertical slice; neither is established by the ACL tests alone.
