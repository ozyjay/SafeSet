[CmdletBinding()]
param(
    [string]$SourceApp,
    [string]$DestinationDirectory,
    [switch]$Build,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $IsMacOS) {
    throw 'SafeSet.app can only be installed on macOS.'
}
if ($Build -and $PSBoundParameters.ContainsKey('SourceApp')) {
    throw 'Do not combine -Build with -SourceApp; the build output is used automatically.'
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($Build) {
    $null = & (Join-Path $PSScriptRoot 'build-macos-app.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'SafeSet.app build failed.' }
}

if ([string]::IsNullOrWhiteSpace($SourceApp)) {
    $SourceApp = Join-Path $repo 'dist/SafeSet.app'
}
if (-not (Test-Path -LiteralPath $SourceApp -PathType Container)) {
    throw 'SafeSet.app was not found. Build it first or pass -SourceApp.'
}
$sourcePath = (Resolve-Path -LiteralPath $SourceApp).Path
$infoPlist = Join-Path $sourcePath 'Contents/Info.plist'
if (-not (Test-Path -LiteralPath $infoPlist -PathType Leaf)) {
    throw 'The source is not a complete macOS application bundle.'
}
$bundleIdentifier = & /usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' $infoPlist
if ($LASTEXITCODE -ne 0 -or $bundleIdentifier -ne 'org.ozyjay.SafeSet') {
    throw 'The source application does not have the expected SafeSet bundle identifier.'
}
& /usr/bin/codesign --verify --strict $sourcePath
if ($LASTEXITCODE -ne 0) { throw 'The source application signature is invalid.' }

if ([string]::IsNullOrWhiteSpace($DestinationDirectory)) {
    $userProfile = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
    $DestinationDirectory = Join-Path $userProfile 'Applications'
}
New-Item -ItemType Directory -Force -Path $DestinationDirectory | Out-Null
$destinationRoot = (Resolve-Path -LiteralPath $DestinationDirectory).Path
$destinationPath = Join-Path $destinationRoot 'SafeSet.app'
if ($sourcePath -eq $destinationPath) {
    throw 'The source and installation paths are the same.'
}
if ((Test-Path -LiteralPath $destinationPath) -and -not $Force) {
    throw 'SafeSet.app is already installed. Re-run with -Force to replace it.'
}

$operationId = [Guid]::NewGuid().ToString('N')
$stagingPath = Join-Path $destinationRoot ".SafeSet.app.install-$operationId"
$backupPath = Join-Path $destinationRoot ".SafeSet.app.backup-$operationId"
$previousMoved = $false

try {
    & /usr/bin/ditto $sourcePath $stagingPath
    if ($LASTEXITCODE -ne 0) { throw 'Copying the application bundle failed.' }
    & /usr/bin/codesign --verify --strict $stagingPath
    if ($LASTEXITCODE -ne 0) { throw 'The staged application signature is invalid.' }

    if (Test-Path -LiteralPath $destinationPath) {
        Move-Item -LiteralPath $destinationPath -Destination $backupPath
        $previousMoved = $true
    }

    try {
        Move-Item -LiteralPath $stagingPath -Destination $destinationPath
        & /usr/bin/codesign --verify --strict $destinationPath
        if ($LASTEXITCODE -ne 0) { throw 'The installed application signature is invalid.' }
    }
    catch {
        if (Test-Path -LiteralPath $destinationPath) {
            Remove-Item -LiteralPath $destinationPath -Recurse -Force
        }
        if ($previousMoved -and (Test-Path -LiteralPath $backupPath)) {
            Move-Item -LiteralPath $backupPath -Destination $destinationPath
            $previousMoved = $false
        }
        throw
    }

    if ($previousMoved) {
        Remove-Item -LiteralPath $backupPath -Recurse -Force
        $previousMoved = $false
    }
}
finally {
    if (Test-Path -LiteralPath $stagingPath) {
        Remove-Item -LiteralPath $stagingPath -Recurse -Force
    }
    if ($previousMoved -and (Test-Path -LiteralPath $backupPath) -and
        -not (Test-Path -LiteralPath $destinationPath)) {
        Move-Item -LiteralPath $backupPath -Destination $destinationPath
    }
}

Write-Output $destinationPath
