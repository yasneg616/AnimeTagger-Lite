[CmdletBinding()]
param(
    [string]$OutputRoot = 'release',
    [switch]$DebugConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build_common.ps1')

Invoke-AnimeTaggerBuild -Variant 'cuda' -OutputRoot $OutputRoot -DebugConsole:$DebugConsole
