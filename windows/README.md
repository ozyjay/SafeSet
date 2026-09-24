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

The current private-bundle storage implementation deliberately requires POSIX ownership
and mode checks. Therefore Windows protection/restoration remains **not operational**
until SafeSet has an equivalent tested Windows ACL boundary.

Before a Windows build may handle operational data:

1. implement private bundle directory/file ACL creation and validation;
2. ensure only the current user (and unavoidable system/admin principals) can access it;
3. reject inherited or overly broad permissions according to an explicit policy;
4. test symlinks/reparse points, repository paths, cloud/network locations and no-clobber writes;
5. exercise bundle creation/read/restoration with synthetic fixtures on Windows 11;
6. update the threat model and verification record with tested behaviour.

Do not bypass the existing fail-closed storage check merely to make the Windows UI work.


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

The interactive review buttons intentionally stop at preview mode. Do not replace
that warning with a publication path until Windows ACL protection is implemented
and verified.
