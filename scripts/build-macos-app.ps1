param(
    [switch]$CreateDmg
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$package = Join-Path $repo 'macos/SafeSetMac'
$build = Join-Path $repo 'build/macos'
$app = Join-Path $repo 'dist/SafeSet.app'
$python = Join-Path $repo '.venv/bin/python'
$iconSource = Join-Path $repo 'assets/safeset-app-icon-1024.png'
$iconCatalog = Join-Path $build 'SafeSetAssets.xcassets'
$iconSet = Join-Path $iconCatalog 'AppIcon.appiconset'
$compiledIcons = Join-Path $build 'compiled-icons'
$iconFile = Join-Path $compiledIcons 'AppIcon.icns'

if (-not (Test-Path $python)) { throw 'Create the project virtual environment first.' }
if (-not (Test-Path $iconSource -PathType Leaf)) { throw 'SafeSet app icon source is missing.' }
& $python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Install the mac-app dependency group first.' }

New-Item -ItemType Directory -Force $build | Out-Null
if (Test-Path $iconCatalog) { Remove-Item -LiteralPath $iconCatalog -Recurse -Force }
if (Test-Path $compiledIcons) { Remove-Item -LiteralPath $compiledIcons -Recurse -Force }
New-Item -ItemType Directory $iconSet, $compiledIcons | Out-Null
Copy-Item -LiteralPath (Join-Path $repo 'assets/AppIcon.appiconset/Contents.json') `
    -Destination $iconSet
$iconSizes = @(
    @{ Name = 'icon_16x16.png'; Pixels = 16 },
    @{ Name = 'icon_16x16@2x.png'; Pixels = 32 },
    @{ Name = 'icon_32x32.png'; Pixels = 32 },
    @{ Name = 'icon_32x32@2x.png'; Pixels = 64 },
    @{ Name = 'icon_128x128.png'; Pixels = 128 },
    @{ Name = 'icon_128x128@2x.png'; Pixels = 256 },
    @{ Name = 'icon_256x256.png'; Pixels = 256 },
    @{ Name = 'icon_256x256@2x.png'; Pixels = 512 },
    @{ Name = 'icon_512x512.png'; Pixels = 512 },
    @{ Name = 'icon_512x512@2x.png'; Pixels = 1024 }
)
foreach ($size in $iconSizes) {
    $destination = Join-Path $iconSet $size.Name
    & /usr/bin/sips -z $size.Pixels $size.Pixels $iconSource --out $destination | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "App icon generation failed for $($size.Name)." }
}
& /usr/bin/xcrun actool $iconCatalog --compile $compiledIcons --platform macosx `
    --minimum-deployment-target 14.0 --app-icon AppIcon `
    --output-partial-info-plist (Join-Path $build 'AppIcon.plist')
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $iconFile -PathType Leaf)) {
    throw 'App icon packaging failed.'
}
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
    -destination 'platform=macOS,arch=arm64' `
    -derivedDataPath (Join-Path $build 'DerivedData') `
    CODE_SIGNING_ALLOWED=NO OTHER_SWIFT_FLAGS=-disable-sandbox build
if ($LASTEXITCODE -ne 0) { throw 'SwiftUI Xcode build failed.' }
$builtApp = Join-Path $build 'DerivedData/Build/Products/Release/SafeSetMac.app'
if (-not (Test-Path $builtApp)) { throw 'Xcode did not produce the app.' }

if (Test-Path $app) { Remove-Item -Recurse -Force $app }
Copy-Item -LiteralPath $builtApp -Destination $app -Recurse
$helpers = Join-Path $app 'Contents/Helpers/SafeSetBackend'
$appResources = Join-Path $app 'Contents/Resources'
$resources = Join-Path $appResources 'SafeSetBackend'
New-Item -ItemType Directory -Force $helpers, $resources | Out-Null
Copy-Item (Join-Path $build 'python/safeset-backend/safeset-backend') $helpers
Copy-Item (Join-Path $build 'python/safeset-backend/_internal/*') $resources -Recurse
Copy-Item -LiteralPath (Join-Path $repo 'HOWTO.md') `
    -Destination (Join-Path $appResources 'HOWTO.md')
Copy-Item -LiteralPath $iconFile -Destination (Join-Path $appResources 'AppIcon.icns')
Copy-Item -LiteralPath (Join-Path $compiledIcons 'Assets.car') -Destination $appResources
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
