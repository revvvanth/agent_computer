param(
    [Parameter(Mandatory = $true)][string]$Destination,
    [switch]$IncludeReports
)
$ErrorActionPreference = 'Stop'
$researchRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$exportPath = [IO.Path]::GetFullPath($Destination)
# Create a new project; never merge into or overwrite an existing destination.
if (Test-Path -LiteralPath $exportPath) { throw 'Destination already exists. Choose a new folder.' }
if ($researchRoot.StartsWith($exportPath.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Destination cannot be an ancestor of this project.'
}
$excluded = @('.git', '.gitnexus', '.venv', '.cache', '.pytest_cache', '__pycache__',
    'vendor', 'workspaces', '.env', '.env.example', '.kareos-parent-guard.json',
    'standalone-export.json')
if (-not $IncludeReports) { $excluded += 'reports' }
$items = @(Get-ChildItem -LiteralPath $researchRoot -Force | Where-Object {
    $_.Name -notin $excluded -and $_.Name -notlike '.baseline-*.txt' -and $_.Extension -ne '.pyc'
})
New-Item -ItemType Directory -Path $exportPath | Out-Null
foreach ($item in $items) {
    Copy-Item -LiteralPath $item.FullName -Destination $exportPath -Recurse
}
# Retain the summary even when raw trial artifacts are excluded.
if (-not $IncludeReports) {
    New-Item -ItemType Directory -Path (Join-Path $exportPath 'reports') | Out-Null
    Copy-Item -LiteralPath (Join-Path $researchRoot 'reports/DEEP_RESULTS.md') -Destination (Join-Path $exportPath 'reports/DEEP_RESULTS.md')
    foreach ($validationFile in @('STANDALONE_VALIDATION.md','standalone-validation.xml','portable-validation.xml','portable-smoke.json')) {
        $validationSource = Join-Path $researchRoot ('reports/' + $validationFile)
        if (Test-Path -LiteralPath $validationSource) { Copy-Item -LiteralPath $validationSource -Destination (Join-Path $exportPath ('reports/' + $validationFile)) }
    }
}
@{source_project=$researchRoot; exported_at=(Get-Date).ToUniversalTime().ToString('o');
  reports_included=[bool]$IncludeReports; credentials_included=$false;
  instructions='Run setup.ps1, then configure the new .env. Virtual environments and vendor checkouts must be rebuilt.'
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $exportPath 'standalone-export.json') -Encoding UTF8
Write-Host ('Standalone project exported to ' + $exportPath)
Write-Host 'Run setup.ps1 there. Copy only the required RESEARCH_* credentials into its .env for live tests.'
