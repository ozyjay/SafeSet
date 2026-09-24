$ErrorActionPreference = 'Stop'

if (-not $IsWindows) {
    throw 'Run this bootstrap script on Windows.'
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target = Join-Path $repo 'windows/SafeSetWindows'

if (Test-Path $target) {
    throw 'windows/SafeSetWindows already exists; refusing to overwrite it.'
}

dotnet --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw '.NET SDK is required.'
}

$templates = dotnet new list winui 2>$null
if ($LASTEXITCODE -ne 0 -or -not ($templates -match 'winui')) {
    throw 'Install the WinUI templates first: dotnet new install Microsoft.WindowsAppSDK.WinUI.CSharp.Templates'
}

dotnet new winui -n SafeSetWindows -o $target
if ($LASTEXITCODE -ne 0) {
    throw 'WinUI project creation failed.'
}

& (Join-Path $repo 'scripts/update-windows-ux.ps1')
if ($LASTEXITCODE -ne 0) {
    throw 'SafeSet Windows UX overlay failed.'
}

Write-Output $target
