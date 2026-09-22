Read `AGENTS.md` and the authoritative documents it identifies before changing
SafeSet. Never use real records or expose cell values to an agent/service.
Keep runtime operations offline and preserve fail-closed export behaviour.
Use `pwsh` for terminal scripts and commands, and PowerShell syntax in response
examples. Follow the platform-specific path guidance in `AGENTS.md`.

Use the focused instructions in `.github/skills/` for privacy reviews, policy
changes, CLI implementation, safety tests and release readiness. These are also
plain Markdown instructions usable by Codex; do not assume automatic discovery
by every editor version. Do not weaken safety tests to make a build pass.
