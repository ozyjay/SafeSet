param([string]$AppPath = 'dist/SafeSet.app')

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$app = (Resolve-Path (Join-Path $repo $AppPath)).Path
$work = (& /usr/bin/mktemp -d).Trim()
$process = $null
try {
    $moved = Join-Path $work 'SafeSet.app'
    Copy-Item -LiteralPath $app -Destination $moved -Recurse
    $iconName = & /usr/libexec/PlistBuddy -c 'Print :CFBundleIconFile' `
        (Join-Path $moved 'Contents/Info.plist')
    $icon = Join-Path $moved "Contents/Resources/$iconName.icns"
    $assetCatalog = Join-Path $moved 'Contents/Resources/Assets.car'
    if ($LASTEXITCODE -ne 0 -or $iconName -ne 'AppIcon' -or
        -not (Test-Path $icon -PathType Leaf) -or
        -not (Test-Path $assetCatalog -PathType Leaf)) {
        throw 'Bundled app icon is missing or not configured.'
    }
    $helper = Join-Path $moved 'Contents/Helpers/SafeSetBackend/safeset-backend'
    $exports = Join-Path $work 'exports'
    $maps = Join-Path $work 'maps'
    $private = Join-Path $work 'private'
    New-Item -ItemType Directory -Force $exports, $maps, $private | Out-Null
    & /bin/chmod 700 $work $exports $maps $private

    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $helper
    $start.UseShellExecute = $false
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.Environment['PATH'] = '/usr/bin:/bin'
    $start.Environment.Remove('PYTHONPATH') | Out-Null
    $start.Environment.Remove('VIRTUAL_ENV') | Out-Null
    $start.Environment.Remove('PYENV_ROOT') | Out-Null
    $process = [System.Diagnostics.Process]::Start($start)
    if (-not $process) { throw 'Bundled helper did not start.' }

    function Invoke-Bridge([string]$Command, [hashtable]$Payload) {
        $request = @{ version = 1; id = [guid]::NewGuid().ToString(); command = $Command; payload = $Payload }
        $process.StandardInput.WriteLine(($request | ConvertTo-Json -Depth 20 -Compress))
        $line = $process.StandardOutput.ReadLine()
        if (-not $line) { throw 'Bundled helper did not answer.' }
        $response = $line | ConvertFrom-Json -AsHashtable
        if ($response.id -ne $request.id) { throw 'Bundled helper returned the wrong request ID.' }
        return $response
    }

    if (-not (Invoke-Bridge 'hello' @{}).ok) { throw 'Protocol handshake failed.' }
    $source = Join-Path $repo 'examples/synthetic_students.xlsx'
    $policy = Join-Path $repo 'examples/example-policy.yaml'
    $loaded = Invoke-Bridge 'load_policy' @{
        source = $source; sheet = $null; policy = $policy
    }
    if (-not $loaded.ok) { throw 'Bundled policy loading failed.' }
    $output = Join-Path $exports 'protected.xlsx'
    $bundle = Join-Path $maps 'bundle.enc'
    $prepared = Invoke-Bridge 'prepare_protection' @{
        source = $source; sheet = $null; output = $output; bundle = $bundle
        drafts = $loaded.result.drafts; threshold = [string]$loaded.result.threshold
    }
    if (-not $prepared.ok -or -not $prepared.result.validation.passed) {
        throw 'Bundled protection review failed.'
    }
    $passphrase = 'synthetic-standalone-passphrase'
    $approved = Invoke-Bridge 'approve_protection' @{
        review_id = $prepared.result.review_id; passphrase = $passphrase
    }
    if (-not $approved.ok -or -not (Test-Path $output) -or -not (Test-Path $bundle)) {
        throw 'Bundled protection publication failed.'
    }
    $restored = Join-Path $private 'restored.xlsx'
    $review = Invoke-Bridge 'prepare_reconstruction' @{
        returned = $output; returned_sheet = $null; source = $source; source_sheet = $null
        bundle = $bundle; output = $restored; passphrase = $passphrase
    }
    if (-not $review.ok -or $review.result.rows -ne 4) {
        throw 'Bundled restoration review failed.'
    }
    $finished = Invoke-Bridge 'approve_reconstruction' @{
        review_id = $review.result.review_id; approved_results = @()
    }
    if (-not $finished.ok -or -not (Test-Path $restored)) {
        throw 'Bundled reconstruction failed.'
    }
    $repeat = Invoke-Bridge 'prepare_reconstruction' @{
        returned = $output; returned_sheet = $null; source = $source; source_sheet = $null
        bundle = $bundle; output = $restored; passphrase = $passphrase
    }
    if ($repeat.ok) { throw 'Existing output was not rejected.' }
    $transcript = @($prepared, $approved, $review, $finished) | ConvertTo-Json -Depth 20
    if ($transcript.Contains('SYNTH-001') -or $transcript.Contains($passphrase)) {
        throw 'Sensitive value appeared in a bridge response.'
    }
    Write-Output 'Standalone relocated helper round trip passed.'
}
finally {
    if ($process) {
        $process.StandardInput.Close()
        if (-not $process.HasExited) { $process.Kill() }
        $process.Dispose()
    }
    if (Test-Path $work) { Remove-Item -LiteralPath $work -Recurse -Force }
}
