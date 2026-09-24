$ErrorActionPreference = 'Stop'

if (-not $IsWindows) {
    throw 'Run this smoke check on Windows.'
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target = Join-Path $repo 'windows/SafeSetWindows'

if (-not (Test-Path $target -PathType Container)) {
    throw 'windows/SafeSetWindows does not exist. Run scripts/bootstrap-windows-app.ps1 first.'
}

& (Join-Path $repo 'scripts/update-windows-ux.ps1')
if ($LASTEXITCODE -ne 0) {
    throw 'SafeSet Windows UX overlay failed.'
}

Push-Location $target
try {
    dotnet build
    if ($LASTEXITCODE -ne 0) {
        throw 'SafeSet Windows UX build failed.'
    }
}
finally {
    Pop-Location
}

Write-Output 'SafeSet Windows UX build passed.'
