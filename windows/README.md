# SafeSet Windows desktop

This branch contains the native WinUI 3 frontend and Windows build scripts. The Python safety engine, bounded JSON-line protocol and CLI remain shared with the `mac` branch. See [the audited branch split](../docs/platform-branches.md).

## Current status — 5 October 2026

The local Python engine and CLI are installed and tested on Windows 11 x64. The native frontend connects to that engine, and a standalone Python helper is built into the development output. Debug builds are for **synthetic testing only** until native interactions have been verified. Release builds refuse workflow execution; there is no operational desktop release claim.

Implemented native paths:

- DOCX protection with explicit identity terms, local paragraph/figure review, comment removal, validation summary, masked passphrase confirmation and approval;
- DOCX restoration with authenticated bundles, exact-token integrity checks and explicit approval;
- one-worksheet workbook protection with an explicit YAML policy and strict validation;
- workbook restoration with individual result-field, analysis-sheet and changed-field approvals; related/editable/region bundles use the corresponding restoration option.

Related-sheet and editable workbook **creation**, region selection, participant reconciliation and result-only workbook restoration remain CLI/shared-engine features without full Windows UI parity. The Windows UI does not edit policies. Source fields remain immutable in its one-worksheet protection path.

## Local setup

Use PowerShell 7, .NET 10+ and an explicitly selected Python 3.12+ interpreter. A working `python3` may create the environment:

```pwsh
python3 -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -e '.[dev,windows-app]'
```

On this PC the existing `.venv/Scripts/python.exe` is Python 3.14.3; `python3` is an inaccessible Store alias and no active pyenv executable was found. Use the explicit virtual-environment path. No global Python or Windows setting was changed by this setup.

For a new native project, install the current WinUI template and bootstrap once:

```pwsh
dotnet new install Microsoft.WindowsAppSDK.WinUI.CSharp.Templates
& ./scripts/bootstrap-windows-app.ps1
```

The project is already bootstrapped on this PC. Build and verify from the repository root:

```pwsh
& ./scripts/build-windows-helper.ps1
& ./scripts/smoke-windows-ux.ps1
# The C# harness links the production transport; it adds no NuGet test dependency.
dotnet build ./windows/BackendTests/BackendTests.csproj --ignore-failed-sources
& ./.venv/Scripts/python.exe -m pytest
& ./.venv/Scripts/python.exe -m ruff check .
```

Bootstrap preserves the reviewed `MainWindow` and `BackendBridge` files. Other template files, helper binaries and build caches are ignored. `update-windows-ux.ps1` checks the source files and adds the helper-copy items to the generated project. Template installation and explicit Python/NuGet dependency restoration may use package repositories. Runtime data processing needs no network.

NuGet restoration uses the ignored `build/nuget-packages` cache, so builds do not depend on a different account's package directory. After a successful restore, use `smoke-windows-ux.ps1 -NoRestore`. A failed previous restore or missing cache still blocks compilation.

## Start the development app

The default launch uses the packaged template. It requires Windows Developer Mode and a working package registration. On this PC registration conflicts with an existing installation; that installation was left untouched. Use the unpackaged development option:

```pwsh
& ./scripts/run-windows-app.ps1 -Unpackaged
```

Normal launch does not restore packages. Add `-Restore` only when preparing or updating dependencies. The unpackaged option uses Microsoft's supported [self-contained Windows App SDK deployment](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/self-contained-deploy/deploy-self-contained-apps) and disables packaged `winapp` launch redirection. It is a development fallback, not a replacement for the packaged-release gate. The Python helper remains a console executable with redirected local pipes; no console window or network listener is created for data processing.

All scripts select x64 and accept `-Configuration Release` where relevant. Release workflow execution stays disabled pending native verification. The CLI entry points are `./.venv/Scripts/safeset.exe` and `./.venv/Scripts/safeset-document.exe`; `safeset desktop` remains the macOS compatibility launcher.

## Destinations and private storage

The Windows UI chooses a folder and new filename without creating a placeholder. A save-file picker could create a file before SafeSet's approval, which would conflict with no-clobber publication. Private bundle selection proposes a new subdirectory; only the shared engine creates it during explicitly approved publication.

Use fixed local NTFS storage outside repositories and cloud-synchronised folders. Maps and exports need separate directories. Existing broad or inheriting private directories are rejected, not repaired. Native ACL creation, file validation, encryption, stale-review rejection and no-clobber publication remain engine responsibilities. C# does not implement its own privacy decisions.

## Verification and remaining release gates

Actual results are in [verification](../docs/verification.md). The complete Windows Python run passed 361 tests with 8 documented skips. The C# transport and relocated helper completed synthetic DOCX and workbook round trips; cancellation, stale reviews, wrong passphrases, missing approvals and malformed response frames were rejected. Both Debug and unpackaged Release frontend builds compiled. The unpackaged app process started.

Native UI automation could not connect to the Computer Use pipe after retry/reset, so no successful dialog, picker, keyboard or masked-secret interaction test is claimed. Packaged registration, privileged wrong-owner and independent second-user ACL checks, full native workbook parity and Windows release packaging/signing remain gaps. The global format check reports existing formatting differences; lint passes. Do not treat those synthetic results as a security audit or a claim of anonymity.
