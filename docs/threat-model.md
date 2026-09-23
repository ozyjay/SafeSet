# Threat model

## macOS app boundary

The SwiftUI process may display headings and explicitly requested category labels
locally. It does not receive source rows, decrypted bundles or identity maps. The
bundled Python helper reads bounded local JSON-line requests and replies with
allowlisted review metadata or fixed error codes. It has no listener or network
client. A passphrase travels through the local child-process pipe and is never
placed in an argument, environment variable, file or protocol response. Python
and Swift cannot guarantee erasure from process memory. An attacker controlling
the same account or either process is outside this boundary. A stale review token
blocks approval; untrusted workbooks are rechecked by the Python domain layer.

The ad-hoc signed local app is for development, not a trusted public release.
Direct distribution needs Developer ID signing and notarisation. Packaging native
Python libraries adds a nested-code signing surface that must be verified on the
release host and on a clean target Mac.

## Version 2 restoration bundle

The protected working copy is untrusted after analysis. A version 2 encrypted
bundle binds a canonical representation of the selected source table, exact random
record IDs, policy decisions, schemas and observed category codebooks. A changed
source, wrong bundle, changed protected source-derived value, extra unapproved
column, unapproved added worksheet or incomplete ID set blocks reconstruction.
Approved added analysis worksheets are validated as bounded tables and their cell
text, or a formula's saved scalar result (including a saved empty string), is
copied into a new static table without preserving formulas, formatting or drawings;
they are not authenticated by the
original bundle. SafeSet does not calculate formulas. The source digest is inside
authenticated ciphertext; it is a compatibility check, not proof of origin or
protection against a compromised local account. New result values are accepted
only for explicitly approved headings and safe spreadsheet text. The reconstructed
workbook contains the original identifying fields and must remain local and
private. Category codes still expose equality and frequency. Bundle loss or
passphrase loss prevents restoration. The bundle never contains a copy of source
rows or dropped personal fields; the selected source key and codebook labels are
necessary reversible secrets. Legacy version 1 maps cannot be used for this flow.

## Version 3 relational restoration bundle

A version 3 bundle binds multiple selected worksheets, their distinct schemas and
policies, one shared random entity map, globally unique random row IDs and per-sheet
codebooks. The bundle also authenticates any explicitly confirmed same-heading
category fields whose random codebooks are shared across sheets. Equal source-key
text in the explicitly declared entity domain receives
the same `entity_id`; no hash or deterministic pseudonym is used. A separate
`record_id` identifies each row for exact restoration. Worksheet removal, addition,
renaming, row reordering, entity-ID substitution, record-ID substitution and
protected-value changes block reconstruction.

The desktop does not ask the operator to choose bundle-bound worksheets during
relational restoration. It derives them only from the authenticated bundle,
requires all of them to remain visible and valid, and treats every other visible
worksheet as untrusted analysis requiring explicit approval. Hidden returned
worksheets fail closed. Added worksheets are allowed only through this separate
review path; their presence is not itself treated as a change to the bundle-bound
worksheet set.

The shared entity ID is intentional linkability. A recipient can learn that rows
across worksheets concern the same entity and can observe which worksheets and
categories that entity appears in. SafeSet evaluates linked frequency patterns but
cannot prevent auxiliary-data re-identification, graph attacks or inference from
participation. Only worksheets genuinely belonging to the same authorised entity
domain may be grouped into one release.

A shared category codebook is separate, optional intentional linkability. It lets
a recipient recognise that the same coded category occurs in different worksheets
and compare its frequency. Heading equality alone never enables this behaviour;
the operator must confirm each eligible field. The control does not establish that
same-named fields have the same semantics, so that remains an operator
responsibility. Unconfirmed fields receive independent random codes.

This is a conservative local tool, not an anonymity or compliance guarantee.
Protect source identities, identity maps, passphrases and restored data. The
operator, policy author, OS and installed dependencies are trusted. The external
analysis service is not trusted with source identities or maps. Treat returned
analysis as untrusted input. Policies contain schema and categories only, never
real identities or credentials.

| Threat | MVP control | Remaining limitation |
| --- | --- | --- |
| Accidental Git commit | Broad ignores; maps/outputs rejected in detected repositories | Git can force-add files; copies and unknown repositories evade detection |
| Accidental source upload | Local workflow, no runtime networking; candidate held in memory | Cannot control manual uploads or editor/cloud backups |
| Hidden/unexpected fields or sheets | Protection selection means protect-and-include; unselected source sheets are excluded; structured table bounds where present, matching headings, exact protected schema, rejection of hidden returned sheets and separate approval for every added analysis worksheet | Incorrectly authored policy or an explicitly approved analysis sheet can still contain inappropriate information |
| Consolidated field authoring | Exact same-named headings appear once with their worksheet scope; decisions are copied to each per-sheet policy and categorical review retains exact per-sheet allowlists | Same-named fields can have different meanings, so an operator may apply an unsuitable common decision |
| Quasi-identifier combinations | All-attribute equivalence classes, small cells, uniqueness indicators | Auxiliary information, homogeneity and semantic sensitivity remain |
| Mapping disclosure | Fernet authenticated encryption, Argon2id, private directory and files | Weak passphrases, unlocked sessions, backups and compromised hosts |
| Deterministic pseudonyms | Fresh UUIDv4 per record per run | ID alone does not remove attribute disclosure risk |
| Cross-sheet linkage | Explicit shared entity domain, fresh UUIDv4 entity IDs, linked-class review | Equality and participation across released worksheets are deliberately visible |
| Cross-sheet category linkage | Explicit confirmation for same-heading coded fields; fresh shared random codebook; authenticated bundle declaration | Category equality and frequency become deliberately visible; matching headings can still have different meanings |
| Category label disclosure | Fresh random codes for approved categorical values in version 2 | Equality, frequencies and combinations remain visible; the encrypted version 2 bundle stores observed codebooks |
| Exact numeric disclosure | Policy version 3 requires bounds and all-attribute group checks but has no precision limit; genuine blank numeric cells remain blank and enter those checks | Exact values, precision and missingness patterns remain visible and may be distinctive, even when category labels are coded |
| Sensitive logging | Private local log accepts only fixed stage and reason codes; no values, headings, paths or exception text | Event timestamps reveal when operations were attempted; inspect output still displays escaped headings |
| Schema drift | Missing/extra columns and duplicate headings rejected; literal headings matched exactly and bounded; Excel Table headers checked against metadata | Same heading can acquire a different meaning; similarly spelled headings remain distinct |
| Malformed/malicious Excel workbook | ZIP expansion and sheet/field bounds, strict shape, cached-result checks for source formulas, source date/time conversion, formula and date/time rejection in bundle-bound returned sheets, saved-result-only formula handling in added analysis sheets, link/hidden-content checks | Saved source or added-analysis formula results can be stale or inconsistent with the formula; exact source dates remain sensitive even when represented as text; no formal parser proof; resource bounds are conservative MVP limits |
| Lost map/key | Explicit operational backup responsibility | No recovery mechanism; identities cannot be recovered from random IDs |
| Incorrect restoration | Authenticated map schema, exact ID coverage, no fuzzy joins | Cannot verify whether external analysis assigned the right result to an ID |
| Added analysis worksheet | Bounded-table validation, short safe cells, saved scalar results required for formulas, explicit per-sheet approval and a stale-review recheck; output is always static | Approved cell text or a stale cached formula result is copied without formatting, is not authenticated by the original bundle and may still be analytically wrong |
| Relational row confusion | Separate entity and record IDs, source-row bindings and exact worksheet coverage | An approved external result may still be analytically incorrect |
| Incorrect legacy coded-label restoration | Explicit source and policy selection, exact source-key coverage, approved coded columns only, category/code grouping check | The version 1 map has no source snapshot or category codebook; a changed workbook with the same keys and grouping cannot be detected |
| Desktop display or clipboard exposure | Aggregate inspection, no cell preview, masked passphrase fields, no network service | Paths and validation summaries are visible on screen; the OS may retain password entry in process memory |
| Remembered private-bundle path | Desktop preferences retain only the last existing `.enc` path, never the passphrase or bundle content; stale paths are removed and the user can forget the path explicitly | The local account, device backups or preference inspection may reveal the bundle filename and location |
| Policy authoring exposure | Field choices are explicit; Remove hides classification, the linking identifier is internally fixed to `direct_identifier`, retained-information choices map to the two permitted retained classifications, and uncertainty remains blocking; the desktop's bulk Remove action requires a selected source key and changes only wholly undecided headings; distinct category values appear only after a local review action; saved policies use private no-clobber storage outside repositories | A policy can contain sensitive headings and category labels; an incorrect retained-information choice may retain inappropriate data; bulk removal can omit fields needed for analysis |

## Encryption and keys

Use a long unique passphrase from a password manager. Minimum 16 characters is a
usability guardrail, not an entropy guarantee. Do not save it in project files,
shell history, environment variables, logs or exports. Keep an authorised backup
of the encrypted map and manage the passphrase separately. Losing either prevents
restoration. Python cannot guarantee wiping plaintext/key material from memory;
swap, crash dumps and process inspection are outside this MVP's protection.

Envelope v1: `SAFESET1\n`, 16 random salt bytes, then a Fernet token. The decrypted
JSON includes its own version and the source column plus UUID-to-source-key map.
The salt affects the derived key, so modification makes authentication fail.
Fernet exposes a token creation timestamp and approximate payload size. It does
not authenticate the external analysis itself or hide file existence.

The SafeSet rename changes the envelope marker and default storage directory.
Earlier bootstrap maps are not accepted by this reader; retain the matching
earlier application version to restore them. Existing external files are never
automatically moved, decrypted or rewritten during a project rename.

The library's [Fernet guidance](https://cryptography.io/en/stable/fernet/) recommends
password-derived keys through Argon2id. Parameters use the second recommended
Argon2id profile in [RFC 9106 §4](https://www.rfc-editor.org/rfc/rfc9106.html#section-4)
(64 MiB, three passes, four lanes), with a 16-byte salt and 32-byte output.
See the [Argon2id API](https://cryptography.io/en/stable/hazmat/primitives/key-derivation-functions/#argon2id).
These sources were checked during bootstrap; this implementation has not received
an independent cryptographic/security audit. Unsupported backends fail without
falling back to weaker encryption.

## Deployment assumptions

Use a private, non-synchronised local filesystem. Map/export separation is not a
check for cloud-sync software. POSIX ownership/mode enforcement is implemented;
Windows ACL support is not established and map operations fail closed there.
The caller must choose an external private output directory for restored data;
restored Excel workbook contains sensitive plaintext and must not be uploaded. Normal exports also need
access control. No special guarantees apply to network filesystems or hostile
concurrent modification. No secure deletion is claimed.
