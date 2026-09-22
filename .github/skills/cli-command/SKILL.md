---
name: cli-command
description: Implement or modify SafeSet CLI commands and approval flows.
---

# Cli Command

Keep domain logic outside cli.py. Treat exception strings, filenames, headings and cell values as untrusted. Use aggregate reports and fixed errors; never echo source values or secret input. For sanitise, validation and review precede approval and any publication. Keep --create-map, export approval and --authorise as distinct actions. Never add a validation bypass. Test cancellation, missing flags, incorrect credentials and no artefacts on pre-publication failure. Update README examples using synthetic data only, in `pwsh` syntax.
