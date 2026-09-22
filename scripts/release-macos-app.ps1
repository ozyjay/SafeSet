param(
    [Parameter(Mandatory=$true)][string]$SigningIdentity,
    [Parameter(Mandatory=$true)][string]$NotaryProfile
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$app = Join-Path $repo 'dist/SafeSet.app'
if (-not (Test-Path $app)) { throw 'Build the app before signing.' }
if ($SigningIdentity -notlike 'Developer ID Application:*') {
    throw 'Use a Developer ID Application signing identity.'
}

# Sign nested Mach-O code first. Apple advises against using codesign --deep to sign.
$mainExecutable = Join-Path $app 'Contents/MacOS/SafeSetMac'
$code = Get-ChildItem -LiteralPath (Join-Path $app 'Contents') -Recurse -File |
    Where-Object {
        $_.FullName -ne $mainExecutable -and
        (& /usr/bin/file -b $_.FullName) -match 'Mach-O'
    } |
    Sort-Object { $_.FullName.Length } -Descending
foreach ($item in $code) {
    & /usr/bin/codesign --force --timestamp --options runtime `
        --sign $SigningIdentity $item.FullName
    if ($LASTEXITCODE -ne 0) { throw 'Nested code signing failed.' }
}
& /usr/bin/codesign --force --timestamp --options runtime `
    --sign $SigningIdentity $mainExecutable
if ($LASTEXITCODE -ne 0) { throw 'App executable signing failed.' }
& /usr/bin/codesign --force --timestamp --options runtime --sign $SigningIdentity $app
if ($LASTEXITCODE -ne 0) { throw 'App bundle signing failed.' }
& /usr/bin/codesign --verify --strict --verbose=2 $app
if ($LASTEXITCODE -ne 0) { throw 'Signed app verification failed.' }

$zip = Join-Path $repo 'dist/SafeSet-notary.zip'
if (Test-Path $zip) { Remove-Item -Force $zip }
Push-Location (Join-Path $repo 'dist')
try { & /usr/bin/ditto -c -k --keepParent 'SafeSet.app' 'SafeSet-notary.zip' }
finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'Notary archive creation failed.' }
& xcrun notarytool submit $zip --keychain-profile $NotaryProfile --wait
if ($LASTEXITCODE -ne 0) { throw 'App notarisation failed.' }
& xcrun stapler staple $app
if ($LASTEXITCODE -ne 0) { throw 'App ticket stapling failed.' }

$dmg = Join-Path $repo 'dist/SafeSet.dmg'
if (Test-Path $dmg) { Remove-Item -Force $dmg }
& /usr/bin/hdiutil create -volname 'SafeSet' -srcfolder $app -ov -format UDZO $dmg
if ($LASTEXITCODE -ne 0) { throw 'Release DMG creation failed.' }
& xcrun notarytool submit $dmg --keychain-profile $NotaryProfile --wait
if ($LASTEXITCODE -ne 0) { throw 'DMG notarisation failed.' }
& xcrun stapler staple $dmg
if ($LASTEXITCODE -ne 0) { throw 'DMG ticket stapling failed.' }
& xcrun stapler validate $dmg
if ($LASTEXITCODE -ne 0) { throw 'DMG ticket validation failed.' }
& /usr/sbin/spctl --assess --type execute --verbose $app
if ($LASTEXITCODE -ne 0) { throw 'Gatekeeper assessment failed.' }
Write-Output $dmg
