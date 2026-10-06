[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$NoBrowser,
    [int]$BackendPort = 8010,
    [int]$FrontendPort = 5180
)

$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $repository '.human-study-runtime'
$statePath = Join-Path $runtime 'processes.json'

if ($Stop) {
    if (-not (Test-Path -LiteralPath $statePath)) {
        Write-Output 'Human-study services are not recorded as running.'
        exit 0
    }
    $state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
    foreach ($processId in @($state.backend_pid, $state.frontend_pid)) {
        if ($processId -and (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
            Stop-Process -Id $processId
        }
    }
    Remove-Item -LiteralPath $statePath
    Write-Output 'Human-study services stopped.'
    exit 0
}

$python = Join-Path $repository '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python environment missing. Create .venv and install backend requirements first.' }
$pnpm = (Get-Command pnpm.cmd -ErrorAction Stop).Source
$web = Join-Path $repository 'system_components\presentation_layer\web_app'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

if (Test-Path -LiteralPath $statePath) {
    throw "A recorded human-study session already exists. Run .\scripts\human_study.ps1 -Stop first."
}

$env:DATABASE_URL = 'sqlite:///./human_study.db'
$secretBytes = New-Object byte[] 48
$random = [Security.Cryptography.RandomNumberGenerator]::Create()
$random.GetBytes($secretBytes)
$random.Dispose()
$env:TOKEN_SECRET = [Convert]::ToBase64String($secretBytes)
$env:ETHICS_APPROVAL_REFERENCE = 'TAR UMT Ethics Committee Checklist - Ng Jing Yong'
$env:STUDY_ACCESS_EMAIL = 'study@example.com'
$env:STUDY_ACCESS_PASSWORD = 'participant'
$env:VITE_API_TARGET = "http://127.0.0.1:$BackendPort"

$backend = Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', $BackendPort) -WorkingDirectory $repository -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'backend.log') -RedirectStandardError (Join-Path $runtime 'backend-error.log') -PassThru
$frontend = Start-Process -FilePath $pnpm -ArgumentList @('exec', 'vite', '--host', '127.0.0.1', '--port', $FrontendPort, '--strictPort') -WorkingDirectory $web -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'frontend.log') -RedirectStandardError (Join-Path $runtime 'frontend-error.log') -PassThru

@{ backend_pid = $backend.Id; frontend_pid = $frontend.Id; started_at = (Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8

try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/health" -TimeoutSec 1 | Out-Null
            Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort/?study=1" -TimeoutSec 1 -UseBasicParsing | Out-Null
            $ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) { throw 'Human-study services did not become ready. Check .human-study-runtime logs.' }
} catch {
    foreach ($processId in @($backend.Id, $frontend.Id)) {
        if (Get-Process -Id $processId -ErrorAction SilentlyContinue) { Stop-Process -Id $processId }
    }
    Remove-Item -LiteralPath $statePath -ErrorAction SilentlyContinue
    throw
}

$studyUrl = "http://127.0.0.1:$FrontendPort/?study=1#/login"
Write-Output "Human-study mode is ready at $studyUrl"
Write-Output 'Study sign-in: study@example.com / participant'
Write-Output 'Use pseudonymous participant codes only. Stop services with: .\scripts\human_study.ps1 -Stop'
if (-not $NoBrowser) { Start-Process $studyUrl }
