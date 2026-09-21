# Implementation plan

## Milestone 1: bootstrap (before implementation)

Establish package layout, the twelve invariants, architecture, threat model,
policy contract, synthetic fixtures and five reusable agent skills. Use stdlib
CSV rather than a dataframe dependency: preserve exact source identifiers such
as leading-zero strings and reject malformed rows explicitly.

## Milestone 2: smallest useful vertical slice

1. Bounded strict CSV ingestion and duplicate-key-rejecting YAML policy loading.
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

An offline Tk desktop interface now presents the existing inspect, export and
restore workflow. It does not edit policies or change the validation model.

## Dataset-owner choices

Which attributes are necessary? What equivalence-class threshold is appropriate?
Where are the private map directory and restored files stored and backed up?
Who may approve export and restoration? Is the intended external service suitable?
The supplied synthetic policy is illustrative, not an institutional policy.
