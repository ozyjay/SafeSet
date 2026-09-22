---
name: release-review
description: Assess SafeSet release readiness and report the remaining evidence gaps.
---

# Release Review

Read docs/development-plan.md and docs/threat-model.md. Run the full safety suite, lint/format checks, build the wheel and smoke-test the installed CLI using `pwsh` commands. Inspect wheel contents and dependency versions. Check tracked artefacts for maps, keys, source datasets and restored outputs without printing any discovered sensitive values. Review documentation against actual flags and limitations. Report exact checks and platform gaps; a green suite is not a security audit. Do not publish or tag a release unless explicitly requested.
