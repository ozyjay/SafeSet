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
| Hidden/unexpected columns | Exact source and output schema; no passthrough | Incorrectly authored policy can still select inappropriate attributes |
| Quasi-identifier combinations | All-attribute equivalence classes, small cells, uniqueness indicators | Auxiliary information, homogeneity and semantic sensitivity remain |
| Mapping disclosure | Fernet authenticated encryption, Argon2id, private directory and files | Weak passphrases, unlocked sessions, backups and compromised hosts |
| Deterministic pseudonyms | Fresh UUIDv4 per record per run | ID alone does not remove attribute disclosure risk |
| Sensitive logging | Fixed error messages, aggregate findings, no cell samples | Inspect displays escaped headings, which may themselves contain sensitive text |
| Schema drift | Missing/extra columns and duplicate headings rejected | Same heading can acquire a different meaning |
| Malformed/malicious CSV | UTF-8, size/row/column/field limits, strict shape, formula/control checks | No formal parser proof; resource bounds are conservative MVP limits |
| Lost map/key | Explicit operational backup responsibility | No recovery mechanism; identities cannot be recovered from random IDs |
| Incorrect restoration | Authenticated map schema, exact ID coverage, no fuzzy joins | Cannot verify whether external analysis assigned the right result to an ID |

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
restored CSV is plaintext and must not be uploaded. Normal exports also need
access control. No special guarantees apply to network filesystems or hostile
concurrent modification. No secure deletion is claimed.
