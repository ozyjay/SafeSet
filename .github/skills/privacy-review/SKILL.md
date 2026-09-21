---
name: privacy-review
description: Review SafeSet changes against its local privacy and mapping boundaries.
---

# Privacy Review

Read docs/threat-model.md and docs/data-safety-model.md. Trace source values through candidate, output, errors and mapping. Check new fields fail closed, map payload remains minimal, all retained attributes enter risk grouping, and no value reaches logs or networks. Check filesystem paths after symlink resolution and map/export separation. Report concrete findings with severity and file references; distinguish tested properties from assumptions. Do not upload any dataset for review.
