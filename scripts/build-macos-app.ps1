param(
    [switch]$CreateDmg
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$package = Join-Path $repo 'macos/SafeSetMac'
$build = Join-Path $repo 'build/macos'
$app = Join-Path $repo 'dist/SafeSet.app'
$python = Join-Path $repo '.venv/bin/python'

if (-not (Test-Path $python)) { throw 'Create the project virtual environment first.' }
& $python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Install the mac-app dependency group first.' }

New-Item -ItemType Directory -Force $build | Out-Null
$env:PYINSTALLER_CONFIG_DIR = Join-Path $build 'pyinstaller-config'
New-Item -ItemType Directory -Force $env:PYINSTALLER_CONFIG_DIR | Out-Null
& $python -m PyInstaller --noconfirm --clean --onedir --console `
    --name safeset-backend --target-arch arm64 `
    --distpath (Join-Path $build 'python') `
    --workpath (Join-Path $build 'pyinstaller-work') `
    --specpath $build (Join-Path $repo 'src/safeset/bridge_entry.py')
if ($LASTEXITCODE -ne 0) { throw 'Python helper build failed.' }

xcodebuild -quiet -project (Join-Path $package 'SafeSetMac.xcodeproj') `
    -scheme SafeSetMac -configuration Release `
    -derivedDataPath (Join-Path $build 'DerivedData') `
    CODE_SIGNING_ALLOWED=NO OTHER_SWIFT_FLAGS=-disable-sandbox build
if ($LASTEXITCODE -ne 0) { throw 'SwiftUI Xcode build failed.' }
$builtApp = Join-Path $build 'DerivedData/Build/Products/Release/SafeSetMac.app'
if (-not (Test-Path $builtApp)) { throw 'Xcode did not produce the app.' }

if (Test-Path $app) { Remove-Item -Recurse -Force $app }
Copy-Item -LiteralPath $builtApp -Destination $app -Recurse
$helpers = Join-Path $app 'Contents/Helpers/SafeSetBackend'
$resources = Join-Path $app 'Contents/Resources/SafeSetBackend'
New-Item -ItemType Directory -Force $helpers, $resources | Out-Null
Copy-Item (Join-Path $build 'python/safeset-backend/safeset-backend') $helpers
Copy-Item (Join-Path $build 'python/safeset-backend/_internal/*') $resources -Recurse
New-Item -ItemType SymbolicLink -Path (Join-Path $helpers '_internal') `
    -Target '../../Resources/SafeSetBackend' | Out-Null

& /usr/bin/codesign --force --sign - $app
if ($LASTEXITCODE -ne 0) { throw 'Local ad-hoc app signing failed.' }
& /usr/bin/codesign --verify --strict $app
if ($LASTEXITCODE -ne 0) { throw 'Local app signature verification failed.' }

$zip = Join-Path $repo 'dist/SafeSet-local.zip'
if (Test-Path $zip) { Remove-Item -Force $zip }
Push-Location (Join-Path $repo 'dist')
try { & /usr/bin/ditto -c -k --keepParent 'SafeSet.app' 'SafeSet-local.zip' }
finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'Local ZIP creation failed.' }

if ($CreateDmg) {
    $dmg = Join-Path $repo 'dist/SafeSet-local.dmg'
    if (Test-Path $dmg) { Remove-Item -Force $dmg }
    & /usr/bin/hdiutil create -volname 'SafeSet' -srcfolder $app -ov -format UDZO $dmg
    if ($LASTEXITCODE -ne 0) { throw 'Local DMG creation failed.' }
}
Write-Output $app
