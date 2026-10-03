param([int]$Port = 8766, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$reviewRoot = Split-Path -Parent $PSScriptRoot
$reviewData = Join-Path $reviewRoot 'data\tag-visual-review'
$reviewManifest = Join-Path $reviewData 'server.json'

function Get-ReviewHealth([string]$Url) {
    try {
        if ($Url -notmatch '^http://127\.0\.0\.1:[0-9]{1,5}$') { return $null }
        $health = Invoke-RestMethod -Uri ($Url + '/api/health') -TimeoutSec 2 -Proxy $null
        if ($health.app -eq 'anime-tagger-icon-review') { return $health }
    } catch { return $null }
    return $null
}

$reviewUrl = $null
if (Test-Path -LiteralPath $reviewManifest) {
    try {
        $reviewSaved = Get-Content -LiteralPath $reviewManifest -Raw | ConvertFrom-Json
        $reviewHealth = Get-ReviewHealth $reviewSaved.url
        if ($reviewHealth -and $reviewHealth.instance -eq $reviewSaved.instance) { $reviewUrl = $reviewSaved.url }
    } catch { }
}
if (-not $reviewUrl) {
    $reviewExecutable = Join-Path $reviewRoot 'AnimeTaggerLite.exe'
    if (Test-Path -LiteralPath $reviewExecutable) {
        $reviewArguments = @('--review-icons', '--port')
    } else {
        $reviewExecutable = Join-Path $reviewRoot '.venv311-cuda\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $reviewExecutable)) {
            $reviewExecutable = Join-Path $reviewRoot '.venv-cyber\Scripts\python.exe'
        }
        if (-not (Test-Path -LiteralPath $reviewExecutable)) {
            $reviewPythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
            if (-not $reviewPythonCommand) { throw 'Python 3.10+ or the portable AnimeTaggerLite.exe is required.' }
            $reviewExecutable = $reviewPythonCommand.Source
        }
        $reviewArguments = @('-X', 'utf8', '-m', 'app.tag_visual_review', '--port')
    }
    New-Item -ItemType Directory -Path $reviewData -Force | Out-Null
    $reviewPort = $Port
    $reviewAvailable = $false
    for ($reviewAttempt = 0; $reviewAttempt -lt 10; $reviewAttempt++) {
        if ($reviewPort -lt 1 -or $reviewPort -gt 65535) { throw 'No valid local review port is available.' }
        $reviewListener = Get-NetTCPConnection -State Listen -LocalPort $reviewPort -ErrorAction SilentlyContinue
        if (-not $reviewListener) { $reviewAvailable = $true; break }
        $reviewPort++
    }
    if (-not $reviewAvailable) { throw 'All requested local review ports are in use.' }
    $reviewProcess = Start-Process -FilePath $reviewExecutable -ArgumentList ($reviewArguments + @($reviewPort)) -WorkingDirectory $reviewRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $reviewData 'server.stdout.log') -RedirectStandardError (Join-Path $reviewData 'server.stderr.log')
    $reviewCandidate = 'http://127.0.0.1:' + $reviewPort
    $reviewDeadline = [DateTime]::UtcNow.AddSeconds(180)
    while ([DateTime]::UtcNow -lt $reviewDeadline) {
        $reviewProcess.Refresh()
        if ($reviewProcess.HasExited) { throw ('Review server failed to start. See ' + (Join-Path $reviewData 'server.stderr.log')) }
        $reviewHealth = Get-ReviewHealth $reviewCandidate
        if ($reviewHealth -and (Test-Path -LiteralPath $reviewManifest)) {
            try {
                $reviewStarted = Get-Content -LiteralPath $reviewManifest -Raw | ConvertFrom-Json
                if ($reviewStarted.url -eq $reviewCandidate -and $reviewStarted.instance -eq $reviewHealth.instance) {
                    $reviewUrl = $reviewCandidate
                    break
                }
            } catch { }
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $reviewUrl) { throw 'Review server did not become ready. Check its local log and retry.' }
}
if (-not $NoBrowser) { Start-Process -FilePath $reviewUrl }
Write-Output $reviewUrl
