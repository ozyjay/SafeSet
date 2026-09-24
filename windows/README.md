# SafeSet Windows desktop

SafeSet targets a native Windows experience using **WinUI 3 with the Windows App SDK**.
The Windows shell must consume the same bounded JSON-line desktop protocol and Python
safety engine as the macOS SwiftUI app. It must not duplicate or weaken safety logic.

## Supported target

Initial target:

- Windows 11 x64
- .NET 10+
- WinUI 3 / Windows App SDK
- packaged desktop application
- PowerShell 7+ (`pwsh`), with Windows Developer Mode enabled for launch

Use the current Microsoft WinUI project template rather than pinning a stale template
or Windows App SDK package version in this repository before the Windows build is
actively maintained.

From PowerShell 7 on the Windows development machine, at the repository root:

```pwsh
dotnet new install Microsoft.WindowsAppSDK.WinUI.CSharp.Templates
& ./scripts/bootstrap-windows-app.ps1
& ./scripts/smoke-windows-ux.ps1
& ./scripts/run-windows-app.ps1
```

The bootstrap script creates `SafeSetWindows.csproj` and its supporting template
files directly in `windows/SafeSetWindowsUX`, preserving the source-controlled
`MainWindow.xaml` and `MainWindow.xaml.cs`. The project name and C# namespace remain
`SafeSetWindows`. Temporary scaffolding is retained under the ignored `build` directory.

If the WinUI project already exists in `windows/SafeSetWindowsUX`, launch it directly:

```pwsh
& ./scripts/run-windows-app.ps1
```

The frontend lives in `windows/SafeSetWindowsUX`; all scripts use that directory.
Generated template files are ignored by Git; the two reviewed `MainWindow` source
files remain tracked. The old `windows/SafeSetWindows` directory is no longer used.
If you previously bootstrapped there, run bootstrap again to create the project in
the correct directory; the old directory is left untouched.

Both smoke and launch scripts validate the frontend project, select
the x64 platform and accept `-Configuration Release` (the default is `Debug`).
The smoke script builds only; the launch script uses the template's packaged
`dotnet run` support. Both restore the caller's working directory after completion
or failure. `& ./scripts/update-windows-ux.ps1` remains a compatibility command
that checks the project and source files; copying an overlay is no longer needed.
Edit the tracked `MainWindow` files directly in `windows/SafeSetWindowsUX`.

For an offline build after a successful restore, run
`& ./scripts/smoke-windows-ux.ps1 -NoRestore`. This does not fetch missing packages;
an absent or failed previous restore still blocks the build.

Template installation and the initial NuGet restore need network access. The
scripts do not install SDKs or templates or enable Developer Mode automatically.
See Microsoft's [WinUI command-line setup](https://learn.microsoft.com/en-us/windows/apps/get-started/start-here)
for prerequisites and packaged launch troubleshooting.

## Architecture

```text
WinUI 3 shell
    |
    | bounded JSON-line protocol over stdin/stdout
    v
bundled SafeSet Python helper
    |
    +-- workbook protection/restoration
    +-- document protection/restoration
    +-- validation
    +-- encrypted private bundles
    +-- no-clobber publication
```

The shell owns Windows navigation, file pickers, accessibility, Fluent presentation,
window behaviour and packaging. The Python engine owns every data-handling decision.

## Mandatory Windows release gate

The shared engine implements protected NTFS ACL creation and validation with no
new dependencies. Native tests cover private creation, inheritance, excessive
permissions, links, destination separation and no-clobber publication. This does
**not** yet make desktop protection/restoration operational: encrypted round-trip
verification is blocked by missing offline Python dependencies, and the WinUI
backend controller remains to be implemented.

Before a Windows build may handle operational data:

1. retain the engine's restricted directory/file ACL creation and validation;
2. complete encrypted bundle creation/read/restoration tests with synthetic DOCX fixtures;
3. run the full safety suite, including existing POSIX-specific fixture review;
4. connect the bounded shared backend with native review, approval and masked secrets;
5. verify packaged-helper execution and native interactions on Windows 11;
6. review the threat model and verification record against that actual evidence.

Do not bypass ACL validation or enable publication without the remaining evidence.
Existing broad/inheriting directories are not silently repaired. Only fixed local
NTFS storage is supported; ordinary cloud synchronisation cannot be detected.


## Current UX milestone

The current Windows shell is deliberately usable for UX evaluation before the
sensitive storage boundary is enabled. It includes:

- Windows 11 Mica backdrop and left-hand `NavigationView`;
- Home cards for protect/restore workbook and document workflows;
- native file open/save pickers;
- a document-protection form with explicit identity terms and comment-removal choice;
- a document-restoration form with returned DOCX, bundle and output selection;
- workbook workflow shells matching the established SafeSet terminology;
- Advanced and Help pages explaining the shared-engine boundary;
- a persistent InfoBar making it clear that publication is still disabled on Windows.

The interactive review buttons intentionally stop at preview mode. The current
ACL implementation does not remove the encrypted round-trip and native-controller
release gates. Standalone storage checks can run without external packages:

```pwsh
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
& ./.venv/Scripts/python.exe -m unittest discover -s tests/windows -v
```

Tests create only synthetic artefacts in an external temporary directory. The
encrypted DOCX test explicitly skips when its dependencies are absent; that skip
is a release gap, not a successful encrypted-workflow result.
