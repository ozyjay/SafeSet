#Requires -Version 7.0

$ErrorActionPreference = 'Stop'

if (-not $IsWindows) {
    throw 'Run this script on Windows.'
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target = Join-Path $repo 'windows/SafeSetWindowsUX'

if (-not (Test-Path $target -PathType Container)) {
    throw 'windows/SafeSetWindowsUX does not exist. Restore the frontend sources first.'
}

$project = Join-Path $target 'SafeSetWindows.csproj'
if (-not (Test-Path $project -PathType Leaf)) {
    throw 'SafeSetWindows.csproj was not found in SafeSetWindowsUX. Run scripts/bootstrap-windows-app.ps1 first.'
}

$files = @('MainWindow.xaml', 'MainWindow.xaml.cs')
# Compatibility entry point: UX files now live directly in the project directory.
foreach ($name in $files) {
    $from = Join-Path $target $name
    if (-not (Test-Path -LiteralPath $from -PathType Leaf)) {
        throw "Missing Windows UX source file: $name"
    }
}

Write-Output 'SafeSet Windows UX project is ready.'
Write-Output 'From the repository root, run: & ./scripts/run-windows-app.ps1'
