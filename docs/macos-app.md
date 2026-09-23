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

The build creates `dist/SafeSet.app` and `dist/SafeSet-local.zip`. The smoke
test copies the app to a temporary directory, removes development Python
settings from the helper's environment and runs a synthetic protected workbook
round trip. It also checks that existing output is rejected. It uses no real
student data. To request a development DMG, run
`& ./scripts/build-macos-app.ps1 -CreateDmg` on a Mac whose disk-image service
is available. A development DMG remains ad-hoc signed.

To install an existing build for the current user, run:

```pwsh
& ./scripts/install-macos-app.ps1
```

This verifies the bundle identifier and code signature before installing to
`~/Applications/SafeSet.app`. It will not replace an existing installation
unless `-Force` is supplied. Use `-Build` to build immediately before installing,
or `-SourceApp '/path/to/SafeSet.app'` to install a specific bundle. `-Build` and
`-SourceApp` cannot be combined.

The app can be moved as a single `.app` bundle. The helper executable lives in
`Contents/Helpers/SafeSetBackend`; its dependency files live in
`Contents/Resources/SafeSetBackend`. The helper has no port or network service.
The sidebar Help view renders the bundled `Contents/Resources/HOWTO.md`, which is
copied from the repository's `HOWTO.md` before the app is signed.
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
