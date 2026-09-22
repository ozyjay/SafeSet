# Threat model

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
| Hidden/unexpected columns | Explicit worksheet selection, structured table bounds where present, matching headings, exact output schema, no passthrough | Incorrectly authored policy can still select inappropriate attributes or the wrong worksheets or tables |
| Quasi-identifier combinations | All-attribute equivalence classes, small cells, uniqueness indicators | Auxiliary information, homogeneity and semantic sensitivity remain |
| Mapping disclosure | Fernet authenticated encryption, Argon2id, private directory and files | Weak passphrases, unlocked sessions, backups and compromised hosts |
| Deterministic pseudonyms | Fresh UUIDv4 per record per run | ID alone does not remove attribute disclosure risk |
| Category label disclosure | Fresh random codes for approved categorical values in version 2 | Equality, frequencies and combinations remain visible; no persistent codebook exists |
| Exact numeric disclosure | Version 2 requires bounds, precision and all-attribute group checks | Exact values remain visible and may be distinctive, even when category labels are coded |
| Sensitive logging | Private local log accepts only fixed stage and reason codes; no values, headings, paths or exception text | Event timestamps reveal when operations were attempted; inspect output still displays escaped headings |
| Schema drift | Missing/extra columns and duplicate headings rejected; literal headings matched exactly and bounded; Excel Table headers checked against metadata | Same heading can acquire a different meaning; similarly spelled headings remain distinct |
| Malformed/malicious Excel workbook | ZIP expansion and sheet/field bounds, strict shape, cached-result checks for source formulas, source date/time conversion, formula and date/time rejection in returned files, link/hidden-content checks | Saved source formula results can be stale or inconsistent with the formula; exact source dates remain sensitive even when represented as text; no formal parser proof; resource bounds are conservative MVP limits |
| Lost map/key | Explicit operational backup responsibility | No recovery mechanism; identities cannot be recovered from random IDs |
| Incorrect restoration | Authenticated map schema, exact ID coverage, no fuzzy joins | Cannot verify whether external analysis assigned the right result to an ID |
| Incorrect coded-label restoration | Explicit source and policy selection, exact source-key coverage, approved coded columns only, category/code grouping check | The map has no source snapshot or category codebook; a changed workbook with the same keys and grouping cannot be detected |
| Desktop display or clipboard exposure | Aggregate inspection, no cell preview, masked passphrase fields, no network service | Paths and validation summaries are visible on screen; the OS may retain password entry in process memory |
| Policy authoring exposure | Field choices are explicit; distinct category values appear only after a local review action; saved policies use private no-clobber storage outside repositories | A policy can contain sensitive headings and category labels; an incorrect classification may retain inappropriate data |

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
