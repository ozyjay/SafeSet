[CmdletBinding()]
param(
    [string]$SourceApp,
    [string]$DestinationDirectory,
    [switch]$Build,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Stop-Install([string]$problem, [string]$nextStep) {
    Write-Host "SafeSet was not installed: $problem"
    Write-Host "Next step: $nextStep"
    exit 1
}

try {
if (-not $IsMacOS) {
    Stop-Install 'this installer runs only on macOS.' `
        'Run it on a Mac with PowerShell installed.'
}
if ($Build -and $PSBoundParameters.ContainsKey('SourceApp')) {
    Stop-Install '-Build and -SourceApp cannot be combined.' `
        'Use -Build to create a new app, or -SourceApp to install an existing app.'
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($Build) {
    $null = & (Join-Path $PSScriptRoot 'build-macos-app.ps1')
    if ($LASTEXITCODE -ne 0) {
        Stop-Install 'the macOS app build failed.' `
            'Check the build output, fix the reported issue, then run this installer again.'
    }
}

if ([string]::IsNullOrWhiteSpace($SourceApp)) {
    $SourceApp = Join-Path $repo 'dist/SafeSet.app'
}
if (-not (Test-Path -LiteralPath $SourceApp -PathType Container)) {
    Stop-Install 'the source app was not found.' `
        'Run & ./scripts/install-macos-app.ps1 -Build, or pass -SourceApp with an existing app.'
}
$sourcePath = (Resolve-Path -LiteralPath $SourceApp).Path
$infoPlist = Join-Path $sourcePath 'Contents/Info.plist'
if (-not (Test-Path -LiteralPath $infoPlist -PathType Leaf)) {
    Stop-Install 'the source is not a complete macOS app.' `
        'Build a fresh app with & ./scripts/build-macos-app.ps1, then try again.'
}
$bundleIdentifier = & /usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' $infoPlist
if ($LASTEXITCODE -ne 0 -or $bundleIdentifier -ne 'org.ozyjay.SafeSet') {
    Stop-Install 'the source app is not the expected SafeSet build.' `
        'Choose a SafeSet.app build, or run & ./scripts/install-macos-app.ps1 -Build.'
}
& /usr/bin/codesign --verify --strict $sourcePath
if ($LASTEXITCODE -ne 0) {
    Stop-Install 'the source app signature is invalid.' `
        'Build a fresh app with & ./scripts/build-macos-app.ps1, then try again.'
}

if ([string]::IsNullOrWhiteSpace($DestinationDirectory)) {
    $userProfile = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
    $DestinationDirectory = Join-Path $userProfile 'Applications'
}
New-Item -ItemType Directory -Force -Path $DestinationDirectory | Out-Null
$destinationRoot = (Resolve-Path -LiteralPath $DestinationDirectory).Path
$destinationPath = Join-Path $destinationRoot 'SafeSet.app'
if ($sourcePath -eq $destinationPath) {
    Stop-Install 'the source and destination are the same app.' `
        'Choose a different -DestinationDirectory or a different -SourceApp.'
}
if ((Test-Path -LiteralPath $destinationPath) -and -not $Force) {
    Stop-Install 'SafeSet.app is already installed.' `
        'Re-run the same install command with -Force to replace it.'
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
} catch {
    Write-Host 'SafeSet was not installed: a local copy or validation step failed.'
    Write-Host 'Next step: check the existing app and destination permissions, then retry.'
    exit 1
}
