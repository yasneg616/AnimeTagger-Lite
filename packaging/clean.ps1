[CmdletBinding(SupportsShouldProcess = $true)]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$rootPrefix = $projectRoot.TrimEnd('\') + '\'

function Remove-ProjectArtifact {
    param([Parameter(Mandatory = $true)][string]$Path)

    $target = [System.IO.Path]::GetFullPath($Path)
    if (-not $target.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the project: $target"
    }
    if (Test-Path -LiteralPath $target) {
        if ($PSCmdlet.ShouldProcess($target, 'Remove build artifact')) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }
}

foreach ($relative in @(
    'build',
    'dist',
    'build-final',
    'dist-final',
    '.final-release-smoke',
    'release-candidate',
    'release\_build',
    'release\_pyinstaller',
    'release\portable'
)) {
    Remove-ProjectArtifact -Path (Join-Path $projectRoot $relative)
}

$releaseRoot = Join-Path $projectRoot 'release'
if (Test-Path -LiteralPath $releaseRoot -PathType Container) {
    $buildFiles = Get-ChildItem -LiteralPath $releaseRoot -File | Where-Object {
        $_.Name -like 'AnimeTaggerLite-*-portable.zip' -or
        $_.Name -like 'BUILD-REPORT-*.json' -or
        $_.Name -eq 'BUILD_REPORT.md' -or
        $_.Name -eq 'SHA256SUMS.txt'
    }
    foreach ($file in $buildFiles) {
        Remove-ProjectArtifact -Path $file.FullName
    }
}

if ($WhatIfPreference) {
    Write-Output 'AnimeTagger Lite cleanup preview complete; no files were removed.'
}
else {
    Write-Output 'AnimeTagger Lite build artifacts cleaned. Source, models, validation images, configuration, captions, and user data were not touched.'
}
