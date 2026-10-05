#Requires -Version 7.0
param()
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'Run this script on Windows.' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repo '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Create the Windows virtual environment and install .[dev,windows-app] first.'
}
$target = Join-Path $repo 'windows/SafeSetWindowsUX'
Push-Location $repo
try {
    & $python -m PyInstaller --noconfirm --clean --onedir --console `
        --name SafeSetHelper --paths src `
        --distpath (Join-Path $target 'engine') `
        --workpath (Join-Path $repo 'build/windows-helper/work') `
        --specpath (Join-Path $repo 'build/windows-helper') `
        (Join-Path $repo 'src/safeset/bridge_entry.py')
    if ($LASTEXITCODE -ne 0) { throw 'Windows helper build failed.' }
    & (Join-Path $repo 'scripts/update-windows-ux.ps1')
}
finally { Pop-Location }
Write-Output 'Windows Python helper built locally. Run the backend smoke checks before using the app.'
