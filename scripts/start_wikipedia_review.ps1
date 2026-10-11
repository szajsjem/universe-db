param(
    [string]$KeyFile = "$PSScriptRoot/../.build/openrouter-key.dpapi",
    [string]$Output = '.build/wikipedia-glm-reviewed.db',
    [int]$MaxCandidates = 0,
    [string]$FullWikipedia = '',
    [string]$RecheckCandidate = '',
    [ValidateRange(5, 3600)][int]$NetworkRetrySeconds = 60
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not $env:OPENROUTER_API_KEY -and -not (Test-Path -LiteralPath $KeyFile)) {
    throw 'Set OPENROUTER_API_KEY or provide a DPAPI-encrypted key file.'
}
if (-not $env:OPENROUTER_API_KEY) {
    $protectedKey = Get-Content -LiteralPath $KeyFile | ConvertTo-SecureString
    $env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new('', $protectedKey).Password
}
$reviewArguments = @('-u', 'scripts/review_wikipedia_candidates.py', '--output', $Output,
    '--execute', '--accept-cost', '--timeout', '300', '--max-steps', '20', '--enable-thinking')
if ($MaxCandidates -gt 0) { $reviewArguments += @('--max-candidates', "$MaxCandidates") }
if ($FullWikipedia) { $reviewArguments += @('--full-wikipedia', $FullWikipedia) }
if ($RecheckCandidate) { $reviewArguments += @('--recheck-candidate', $RecheckCandidate) }
try {
    while ($true) {
        if (Test-Path -LiteralPath "$Output.stop") {
            Write-Output "Network recovery cancelled by $Output.stop"
            exit 0
        }
        & python @reviewArguments
        $reviewExitCode = $LASTEXITCODE
        if ($reviewExitCode -ne 75) { exit $reviewExitCode }
        Write-Output "Temporary network failure; resuming saved reviews in $NetworkRetrySeconds seconds. Cancel retries by creating $Output.stop"
        for ($retryElapsed = 0; $retryElapsed -lt $NetworkRetrySeconds; $retryElapsed += 5) {
            Start-Sleep -Seconds ([math]::Min(5, $NetworkRetrySeconds - $retryElapsed))
            if (Test-Path -LiteralPath "$Output.stop") { exit 0 }
        }
    }
} finally {
    Remove-Item Env:/OPENROUTER_API_KEY -ErrorAction SilentlyContinue
}
