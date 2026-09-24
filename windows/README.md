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

Use the current Microsoft WinUI project template rather than pinning a stale template
or Windows App SDK package version in this repository before the Windows build is
actively maintained.

From PowerShell on the Windows development machine:

```pwsh
dotnet new install Microsoft.WindowsAppSDK.WinUI.CSharp.Templates
./scripts/bootstrap-windows-app.ps1
```

The bootstrap script creates the template project only when the target directory does
not already exist.

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
