param(
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"

Write-Host "PowerShell version: $($PSVersionTable.PSVersion)" -ForegroundColor Cyan
Write-Host "PowerShell path: $PSHOME" -ForegroundColor Cyan
Write-Host ""

if ($VerifyOnly) {
    exit 0
}

$RepoRoot = "D:\navy_code\github_code\GenericAgent"
Set-Location -LiteralPath $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

& $Python "frontends\tuiapp_v2.py" @args
$exitCode = $LASTEXITCODE

if ($exitCode -ne $null -and $exitCode -ne 0) {
    Write-Host ""
    Write-Host "tuiapp_v2.py exited with code $exitCode" -ForegroundColor Red
}

Write-Host ""
Write-Host "Press Enter to close this PowerShell 7 window..."
[void][Console]::ReadLine()

if ($exitCode -ne $null) {
    exit $exitCode
}
