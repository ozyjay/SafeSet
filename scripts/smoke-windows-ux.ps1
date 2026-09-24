#Requires -Version 7.0

param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',
    [switch]$NoRestore
)

$ErrorActionPreference = 'Stop'

if (-not $IsWindows) {
    throw 'Run this smoke check on Windows.'
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target = Join-Path $repo 'windows/SafeSetWindowsUX'

if (-not (Test-Path $target -PathType Container)) {
    throw 'windows/SafeSetWindowsUX does not exist. Restore the frontend sources first.'
}

if (-not (Get-Command dotnet -CommandType Application -ErrorAction SilentlyContinue)) {
    throw 'Install the .NET 10 SDK or later, then restart PowerShell.'
}

& (Join-Path $repo 'scripts/update-windows-ux.ps1')

Push-Location $target
try {
    $buildArguments = @('./SafeSetWindows.csproj', '--configuration', $Configuration, '-p:Platform=x64')
    if ($NoRestore) { $buildArguments += '--no-restore' }
    dotnet build @buildArguments
    if ($LASTEXITCODE -ne 0) {
        throw 'SafeSet Windows UX build failed.'
    }
}
finally {
    Pop-Location
}

Write-Output 'SafeSet Windows UX build passed.'
