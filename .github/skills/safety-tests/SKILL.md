---
name: safety-tests
description: Write SafeSet regression tests for privacy and restoration invariants.
---

# Safety Tests

Use clearly invented fixtures and private temporary directories outside the checkout for artefacts. Assert absence of source values in CSV and CLI output; parse/decrypt the map to verify minimality. Test schema drift, free text, rare groups, corrupt maps, malformed/duplicate/missing IDs and restore column collisions. Exercise real encryption; do not mock the property being asserted. Deny socket use in runtime integration tests. Test deterministic bin boundaries separately from random-ID freshness. Preserve failing regressions until behaviour is fixed.
