---
name: policy-schema
description: Change SafeSet policy parsing, classifications or transformations safely.
---

# Policy Schema

Read docs/policy-format.md before changing a field or action. Add rejection tests for unknown keys, ambiguous YAML types, duplicate keys and aliases. Define source and output schemas separately; verify validation recognises the transformed domain. Keep exactly one source key and reserve record_id. Document boundaries and migration/version behaviour; test old policies explicitly. Do not silently reinterpret an unsupported schema or exempt analytical attributes from joint risk checks.
