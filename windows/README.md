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
cd ./windows/SafeSetWindows
dotnet run
```

The bootstrap script creates the local WinUI template project and then applies the
source-controlled SafeSet UX overlay from `windows/SafeSetWindowsUX`.

If the WinUI project already exists, update it without recreating the template:

```pwsh
./scripts/update-windows-ux.ps1
cd ./windows/SafeSetWindows
dotnet run
```

The generated `windows/SafeSetWindows` directory is intentionally ignored by Git.
The reviewed Windows UX source lives in `windows/SafeSetWindowsUX`.

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
