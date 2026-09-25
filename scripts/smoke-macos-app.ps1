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
    $sheetList = Invoke-Bridge 'list_sheets' @{ path = $source }
    $sheet = $sheetList.result.sheets[0]
    $editOutput = Join-Path $exports 'editable.xlsx'
    $editBundle = Join-Path $maps 'editable.enc'
    $editPrepared = Invoke-Bridge 'prepare_relational_protection' @{
        source = $source; sheets = @($sheet); output = $editOutput; bundle = $editBundle
        drafts = @{ $sheet = $loaded.result.drafts }; threshold = [string]$loaded.result.threshold
        validation_profile = 'strict'; editable_fields = @{ $sheet = @('campus') }
    }
    if (-not $editPrepared.ok -or -not $editPrepared.result.analysis_prompt) {
        throw 'Bundled editable-workbook review failed.'
    }
    $editApproved = Invoke-Bridge 'approve_relational_protection' @{
        review_id = $editPrepared.result.review_id; passphrase = $passphrase
    }
    if (-not $editApproved.ok) { throw 'Bundled editable-workbook protection failed.' }
    $editReturned = Join-Path $exports 'editable-returned.xlsx'
    Copy-Item -LiteralPath $editOutput -Destination $editReturned
    $archive = [System.IO.Compression.ZipFile]::Open($editReturned, 'Update')
    try {
        $entry = $archive.GetEntry('xl/worksheets/sheet1.xml')
        $reader = [System.IO.StreamReader]::new($entry.Open())
        try { [xml]$xml = $reader.ReadToEnd() } finally { $reader.Dispose() }
        $namespaces = [System.Xml.XmlNamespaceManager]::new($xml.NameTable)
        $namespaces.AddNamespace('s', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main')
        $first = $xml.SelectSingleNode('//s:c[@r="C2"]/s:is/s:t', $namespaces)
        $second = $xml.SelectSingleNode('//s:c[@r="C4"]/s:is/s:t', $namespaces)
        if (-not $first -or -not $second -or $first.InnerText -eq $second.InnerText) {
            throw 'Synthetic allocation fixture is unsuitable.'
        }
        $firstCode = $first.InnerText
        $first.InnerText = $second.InnerText
        $second.InnerText = $firstCode
        $entry.Delete()
        $replacement = $archive.CreateEntry('xl/worksheets/sheet1.xml')
        $writer = [System.IO.StreamWriter]::new($replacement.Open())
        try { $writer.Write($xml.OuterXml) } finally { $writer.Dispose() }
    } finally { $archive.Dispose() }
    $editRestored = Join-Path $private 'edited-restored.xlsx'
    $editReview = Invoke-Bridge 'prepare_relational_reconstruction' @{
        returned = $editReturned; source = $source; bundle = $editBundle
        output = $editRestored; passphrase = $passphrase
    }
    if (-not $editReview.ok -or $editReview.result.changes[$sheet].campus -ne 2) {
        throw 'Bundled editable-workbook restoration review failed.'
    }
    $editFinished = Invoke-Bridge 'approve_relational_reconstruction' @{
        review_id = $editReview.result.review_id
        approved_results = @{ $sheet = @() }; approved_changes = @{ $sheet = @('campus') }
    }
    if (-not $editFinished.ok -or -not (Test-Path -LiteralPath $editRestored)) {
        throw 'Bundled editable-workbook restoration failed.'
    }
    $transcript = @($prepared, $approved, $review, $finished,
                   $editPrepared, $editApproved, $editReview, $editFinished) | ConvertTo-Json -Depth 20
    if ($transcript.Contains('SYNTH-001') -or $transcript.Contains($passphrase)) {
        throw 'Sensitive value appeared in a bridge response.'
    }
    Write-Output 'Standalone relocated helper legacy and editable round trips passed.'
}
finally {
    if ($process) {
        $process.StandardInput.Close()
        if (-not $process.HasExited) { $process.Kill() }
        $process.Dispose()
    }
    if (Test-Path $work) { Remove-Item -LiteralPath $work -Recurse -Force }
}
