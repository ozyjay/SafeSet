#Requires -Version 7.0

$ErrorActionPreference = 'Stop'

if (-not $IsWindows) {
    throw 'Run this bootstrap script on Windows.'
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target = Join-Path $repo 'windows/SafeSetWindowsUX'

if (Test-Path -LiteralPath (Join-Path $target 'SafeSetWindows.csproj')) {
    throw 'windows/SafeSetWindowsUX is already bootstrapped. Run scripts/run-windows-app.ps1 instead.'
}
foreach ($name in @('MainWindow.xaml', 'MainWindow.xaml.cs')) {
    if (-not (Test-Path -LiteralPath (Join-Path $target $name) -PathType Leaf)) {
        throw 'Windows UX source files are missing. Restore the frontend sources before bootstrapping.'
    }
}

if (-not (Get-Command dotnet -CommandType Application -ErrorAction SilentlyContinue)) {
    throw 'Install the .NET 10 SDK or later, then restart PowerShell.'
}
$sdkVersion = dotnet --version
if ($LASTEXITCODE -ne 0 -or $sdkVersion -notmatch '^(\d+)\.' -or [int]$Matches[1] -lt 10) {
    throw 'The active .NET SDK must be version 10 or later.'
}

# Check the exact project template, not similarly named item templates.
dotnet new winui --help *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Install the WinUI templates first: dotnet new install Microsoft.WindowsAppSDK.WinUI.CSharp.Templates'
}

# Scaffold separately so the template cannot overwrite the reviewed UX sources.
$staging = Join-Path $repo ('build/windows-bootstrap/' + [guid]::NewGuid().ToString('N'))
dotnet new winui -n SafeSetWindows -o $staging
if ($LASTEXITCODE -ne 0) {
    throw 'WinUI project creation failed.'
}

$generated = @(Get-ChildItem -LiteralPath $staging -Force |
    Where-Object { $_.Name -notin @('MainWindow.xaml', 'MainWindow.xaml.cs') })
foreach ($item in $generated) {
    if (Test-Path -LiteralPath (Join-Path $target $item.Name)) {
        throw 'A generated project file already exists in SafeSetWindowsUX; refusing to overwrite it.'
    }
}
New-Item -ItemType Directory -Path $target -Force | Out-Null
foreach ($item in $generated) {
    Copy-Item -LiteralPath $item.FullName -Destination $target -Recurse
}

& (Join-Path $repo 'scripts/update-windows-ux.ps1')

Write-Output $target
