# macOS app build and release

SafeSet's SwiftUI app targets Apple Silicon and macOS 14 or newer. Its bundled
Python helper performs all workbook, policy, validation, encryption and
restoration operations locally. The development app and ZIP are ad-hoc signed.
They are suitable for local testing, not direct public distribution.

## Build and test

Use macOS with Xcode command-line tools, PowerShell and the active pyenv
Python 3.12 or newer. From the repository root:

```pwsh
python3 -m venv .venv
./.venv/bin/Activate.ps1
python3 -m pip install -e '.[dev,mac-app]'
& ./scripts/build-macos-app.ps1
& ./scripts/smoke-macos-app.ps1
& ./.venv/bin/python -m pytest
& ./.venv/bin/ruff check .
swift test --disable-sandbox --package-path macos/SafeSetMac
& /usr/bin/codesign --verify --strict ./dist/SafeSet.app
```

The default configuration is `Release`. To build the native app using Xcode's
`Debug` configuration, run:

```pwsh
& ./scripts/build-macos-app.ps1 -Configuration Debug
```

Use **Terminal → Run Task → SafeSet: Build and run macOS Debug** in VS Code to
build and open the separate **SafeSet Debug** app. The Debug app automatically
uses a known development passphrase only when the
original workbook exactly matches `examples/synthetic_students.xlsx` or
`examples/synthetic_participants.xlsx`. Those bundles are for synthetic testing
only. Other workbooks still prompt for a passphrase, and Release builds never
use the development passphrase. The Debug build has a distinct bundle identifier
and runs from `dist/SafeSet.app`; it does not replace the installed Release app.
The Release and Debug build commands replace the same `dist` path.

Both configurations create `dist/SafeSet.app` and `dist/SafeSet-local.zip`, replacing
the previous local build. Building does not update the installed app. The bundled
Python helper uses the same packaging and safety checks in either configuration.

In VS Code, use **Terminal → Run Build Task** for the default Release build, or
**Terminal → Run Task → SafeSet: Build macOS Debug** for Debug. These workspace
tasks start a separate `pwsh -NoProfile -NonInteractive -File` process and keep
the task terminal open after completion. This avoids returning to the interactive
PowerShell prompt, which can crash in VS Code after the build has finished. The
tasks use the Homebrew PowerShell location on Apple Silicon Macs. They do not
repair the interactive terminal or enable PowerShell script breakpoints.

The equivalent command, from a regular PowerShell terminal in the repository, is:

```pwsh
pwsh -NoProfile -NonInteractive -File ./scripts/build-macos-app.ps1 -Configuration Release
```

The smoke
test copies the app to a temporary directory, removes development Python
settings from the helper's environment and runs a synthetic protected workbook
round trip. It also checks that the app icon generated from
`assets/safeset-app-icon-1024.png` is configured and that existing output is
rejected. It uses no real student data. To request a development DMG, run
`& ./scripts/build-macos-app.ps1 -CreateDmg` on a Mac whose disk-image service
is available. A development DMG remains ad-hoc signed. The build prepares and
signs the new app in a staging directory before replacing existing local build
artefacts. If publication is interrupted, the next build restores any missing
app, ZIP or DMG from its previous-build backup.

To install an existing build for the current user, run:

```pwsh
& ./scripts/install-macos-app.ps1
```

In Restore, validating a participant comparison also shows each selected
worksheet's saved editable fields from the private bundle. It uses the same
passphrase entry as validation, displays no participant rows, and changes no
workbook or bundle. The permission list remains visible if comparison validation
reports a membership-sheet permission error.

This verifies the bundle identifier and code signature before installing to
`~/Applications/SafeSet.app`. It will not replace an existing installation
unless `-Force` is supplied. Use `-Build` to build immediately before installing,
or `-SourceApp '/path/to/SafeSet.app'` to install a specific bundle. `-Build` and
`-SourceApp` cannot be combined. Expected problems, such as a missing build or an
existing installation, print a next step in the console and exit with status 1
without an exception trace.

The app can be moved as a single `.app` bundle. The helper executable lives in
`Contents/Helpers/SafeSetBackend`; its dependency files live in
`Contents/Resources/SafeSetBackend`. The helper has no port or network service.
The sidebar Help view renders the bundled `Contents/Resources/HOWTO.md`, which is
copied from the repository's `HOWTO.md` before the app is signed. It provides
section links and a larger, narrower reading layout.
The View menu provides persistent text-size controls: Command-Plus increases,
Command-Minus decreases and Command-0 restores the default size.
After workbook protection succeeds, a sheet displays the copyable ChatGPT
analysis prompt. A reminder on the home view opens it again during that session;
the same prompt is also available on the Restore workbook page. The prompt asks
for exact record-ID and row preservation. Editing mode creates a version 4 bundle,
shows per-sheet field checkboxes and generates a prompt from those permissions and
approved numeric bounds. Reference sheets have no editable fields. Restoration
shows changed-cell counts and requires approval of each changed field before
applying edits to a copy of the original workbook. The prompt contains no source
cell values, identities, codebooks or passphrase. Version 2/3 append-results mode
remains available by turning off the editing option during protection.
Restore also offers **Compare participants with a membership sheet** for version 4.
It reviews reference-only additions, optional removals and existing field changes
together. A copyable prompt requests a bounded additions proposal sheet when
assignments are missing. Local mappings from authenticated reference-only sheets
and separate participant approvals are required before publication. See HOWTO.md
for the complete flow and supported target layouts; fixed summary ranges need
local review in Excel.
Passphrases pass only through its local standard-input pipe. The protocol is
versioned and rejects malformed requests, stale review tokens and oversized
frames. Every publish operation remains subject to Python's validation and
no-clobber checks.

## Developer ID release

After installing a **Developer ID Application** identity and configuring an
`xcrun notarytool` keychain profile, build and run:

```pwsh
& ./scripts/build-macos-app.ps1
& ./scripts/release-macos-app.ps1 `
    -SigningIdentity 'Developer ID Application: Example (TEAMID)' `
    -NotaryProfile 'safeset-notary'
```

The release script signs nested Mach-O libraries and the helper, signs the app,
verifies its signature, submits and staples the app, builds a direct-download
`dist/SafeSet.dmg`, submits and staples the DMG, then checks Gatekeeper. Do not
publish a development ZIP or an unverified DMG. Run the relocated-app smoke
test and the app itself on a clean Apple Silicon Mac running macOS 14 before
claiming that minimum deployment target.

This checkout has no Developer ID credentials. Notarisation and a macOS 14
runtime check are release gates. The current host's disk-image service did not
create a development DMG, so the local ZIP is the available test artefact.
