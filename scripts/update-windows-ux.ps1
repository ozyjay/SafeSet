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

$files = @('MainWindow.xaml', 'MainWindow.xaml.cs', 'BackendBridge.cs')
# Compatibility entry point: UX files now live directly in the project directory.
foreach ($name in $files) {
    $from = Join-Path $target $name
    if (-not (Test-Path -LiteralPath $from -PathType Leaf)) {
        throw "Missing Windows UX source file: $name"
    }
}

# The project comes from the local WinUI template. Keep helper packaging repeatable
# without checking generated template files into source control.
$helper = Join-Path $target 'engine/SafeSetHelper/SafeSetHelper.exe'
if (Test-Path -LiteralPath $helper -PathType Leaf) {
    [xml]$xml = Get-Content -LiteralPath $project -Raw
    $existing = $xml.SelectSingleNode('/Project/ItemGroup[@Label="SafeSetPythonHelper"]')
    if ($null -eq $existing) {
        $group = $xml.CreateElement('ItemGroup')
        $group.SetAttribute('Label', 'SafeSetPythonHelper')
        $content = $xml.CreateElement('None')
        $content.SetAttribute('Include', 'engine\SafeSetHelper\**\*')
        foreach ($name in @('CopyToOutputDirectory', 'CopyToPublishDirectory')) {
            $element = $xml.CreateElement($name)
            $element.InnerText = 'PreserveNewest'
            [void]$content.AppendChild($element)
        }
        [void]$group.AppendChild($content)
        [void]$xml.Project.AppendChild($group)
        $xml.Save($project)
    } elseif ($existing.FirstChild.Name -eq 'Content') {
        $content = $xml.CreateElement('None')
        foreach ($attribute in $existing.FirstChild.Attributes) { $content.SetAttribute($attribute.Name, $attribute.Value) }
        foreach ($child in @($existing.FirstChild.ChildNodes)) { [void]$content.AppendChild($child.CloneNode($true)) }
        [void]$existing.ReplaceChild($content, $existing.FirstChild)
        $xml.Save($project)
    }
}

Write-Output 'SafeSet Windows UX project is ready.'
Write-Output 'From the repository root, run: & ./scripts/run-windows-app.ps1'
