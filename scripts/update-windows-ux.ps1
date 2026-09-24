$ErrorActionPreference = 'Stop'

if (-not $IsWindows) {
    throw 'Run this script on Windows.'
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$source = Join-Path $repo 'windows/SafeSetWindowsUX'
$target = Join-Path $repo 'windows/SafeSetWindows'

if (-not (Test-Path $target -PathType Container)) {
    throw 'windows/SafeSetWindows does not exist. Run scripts/bootstrap-windows-app.ps1 first.'
}

$project = Join-Path $target 'SafeSetWindows.csproj'
if (-not (Test-Path $project -PathType Leaf)) {
    throw 'SafeSetWindows.csproj was not found. Recreate the WinUI template before applying the UX overlay.'
}

foreach ($name in @('MainWindow.xaml', 'MainWindow.xaml.cs')) {
    $from = Join-Path $source $name
    $to = Join-Path $target $name
    if (-not (Test-Path $from -PathType Leaf)) {
        throw "Missing Windows UX source file: $name"
    }
    Copy-Item -LiteralPath $from -Destination $to -Force
}

Write-Output 'SafeSet Windows UX overlay applied.'
Write-Output "Run: cd '$target'; dotnet run"
