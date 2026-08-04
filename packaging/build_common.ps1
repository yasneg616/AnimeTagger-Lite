Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable $($Arguments -join ' ')"
    }
}

function Resolve-BuildOutputRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$OutputRoot
    )

    if ([System.IO.Path]::IsPathRooted($OutputRoot)) {
        return [System.IO.Path]::GetFullPath($OutputRoot)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $OutputRoot))
}

function Invoke-AnimeTaggerBuild {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('cpu', 'cuda')]
        [string]$Variant,
        [string]$OutputRoot = 'release',
        [switch]$DebugConsole
    )

    $projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $environmentName = if ($Variant -eq 'cpu') { '.venv311-cpu' } else { '.venv311-cuda' }
    $python = Join-Path $projectRoot "$environmentName\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Required Python 3.11 environment is missing: $python"
    }
    $resolvedOutput = Resolve-BuildOutputRoot -ProjectRoot $projectRoot -OutputRoot $OutputRoot

    Push-Location -LiteralPath $projectRoot
    try {
        Invoke-CheckedNative -Executable $python -Arguments @(
            '-c',
            'import platform,sys; assert sys.version_info[:2] == (3, 11), sys.version; assert platform.architecture()[0] == ''64bit''; print(sys.version); print(sys.executable)'
        )
        Invoke-CheckedNative -Executable $python -Arguments @(
            'scripts\build_portable.py',
            '--variant', $Variant,
            '--output-root', $resolvedOutput,
            '--check-only'
        )

        $buildArguments = @(
            'scripts\build_portable.py',
            '--variant', $Variant,
            '--output-root', $resolvedOutput,
            '--clean',
            '--archive'
        )
        if ($DebugConsole) {
            $buildArguments += '--debug-console'
        }
        Invoke-CheckedNative -Executable $python -Arguments $buildArguments
    }
    finally {
        Pop-Location
    }
}
