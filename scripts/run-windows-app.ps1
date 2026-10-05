#Requires -Version 7.0

param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',
    [switch]$Restore,
    [switch]$Unpackaged
)

$ErrorActionPreference = 'Stop'

if (-not $IsWindows) {
    throw 'Run this script on Windows.'
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target = Join-Path $repo 'windows/SafeSetWindowsUX'

if (-not (Get-Command dotnet -CommandType Application -ErrorAction SilentlyContinue)) {
    throw 'Install the .NET 10 SDK or later, then restart PowerShell.'
}

& (Join-Path $repo 'scripts/update-windows-ux.ps1')

Push-Location $target
try {
    $arguments = @('--project', './SafeSetWindows.csproj', '--configuration', $Configuration, '-p:Platform=x64')
    if ($Unpackaged) {
        $arguments += @('--no-launch-profile', '-p:WindowsPackageType=None', '-p:WindowsAppSDKSelfContained=true', '-p:EnableWinAppRunSupport=false')
    }
    if ($Restore) {
        $restoreArguments = @('./SafeSetWindows.csproj', '--packages', (Join-Path $repo 'build/nuget-packages'), '-p:Platform=x64')
        if ($Unpackaged) { $restoreArguments += @('-p:WindowsPackageType=None', '-p:WindowsAppSDKSelfContained=true', '-p:EnableWinAppRunSupport=false') }
        dotnet restore @restoreArguments
        if ($LASTEXITCODE -ne 0) { throw 'Windows dependency restore failed.' }
    }
    $arguments += '--no-restore'
    dotnet run @arguments
    if ($LASTEXITCODE -ne 0) {
        throw 'SafeSet Windows UX launch failed. Check the build output and ensure Windows Developer Mode is enabled.'
    }
}
finally {
    Pop-Location
}
