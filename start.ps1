# EmiMind Services Launcher for Windows PowerShell
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "  Starting EmiMind Full-Stack Development Services  " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

$processes = @()

# Pre-flight check for backing infrastructure
function Test-Port ($port) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $iar = $tcp.BeginConnect("127.0.0.1", $port, $null, $null)
        $wait = $iar.AsyncWaitHandle.WaitOne(300, $false)
        if ($wait -and $tcp.Connected) {
            $tcp.EndConnect($iar)
            $tcp.Close()
            return $true
        }
        $tcp.Close()
        return $false
    } catch {
        return $false
    }
}

$pgUp = Test-Port 5432
$redisUp = Test-Port 6379
$minioUp = Test-Port 9000

# Auto-start MinIO if binary is installed and port 9000 is not running
if (-not $minioUp -and (Get-Command minio -ErrorAction SilentlyContinue)) {
    Write-Host "`nAuto-starting MinIO server (:9000)..." -ForegroundColor Yellow
    $baseDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
    $minioData = Join-Path $baseDir "minio-data"
    if (-not (Test-Path $minioData)) {
        New-Item -ItemType Directory -Path $minioData -Force | Out-Null
    }
    $env:MINIO_ROOT_USER = "minioadmin"
    $env:MINIO_ROOT_PASSWORD = "minioadmin"
    $minioProc = Start-Process -FilePath "minio.exe" -ArgumentList "server `"$minioData`" --console-address :9001 --address :9000" -PassThru -NoNewWindow
    $processes += $minioProc
    Start-Sleep -Seconds 2
    $minioUp = Test-Port 9000
}

Write-Host "`nChecking infrastructure services:" -ForegroundColor Cyan
Write-Host "  - PostgreSQL (:5432) : $(if ($pgUp) { '[OK]' } else { '[NOT RUNNING]' })" -ForegroundColor $(if ($pgUp) { 'Green' } else { 'Red' })
Write-Host "  - Redis      (:6379) : $(if ($redisUp) { '[OK]' } else { '[NOT RUNNING]' })" -ForegroundColor $(if ($redisUp) { 'Green' } else { 'Red' })
Write-Host "  - MinIO      (:9000) : $(if ($minioUp) { '[OK]' } else { '[NOT RUNNING]' })" -ForegroundColor $(if ($minioUp) { 'Green' } else { 'Red' })

if (-not $redisUp -or -not $minioUp -or -not $pgUp) {
    Write-Host "`n[!] Warning: One or more required infrastructure services are not running." -ForegroundColor Yellow
    if (-not $redisUp) { Write-Host "    - arq worker requires Redis on localhost:6379" -ForegroundColor Yellow }
    if (-not $minioUp) { Write-Host "    - Storage requires MinIO on localhost:9000" -ForegroundColor Yellow }
    if (-not $pgUp) { Write-Host "    - Database requires PostgreSQL on localhost:5432" -ForegroundColor Yellow }
    Write-Host ""
}

try {
    Write-Host "[1/3] Starting FastAPI Backend on http://localhost:8000..." -ForegroundColor Green
    $api = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "uv run uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000" -PassThru -NoNewWindow
    $processes += $api

    Write-Host "[2/3] Starting arq Background Worker..." -ForegroundColor Green
    $worker = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "uv run arq services.ingest.worker.WorkerSettings" -PassThru -NoNewWindow
    $processes += $worker

    Write-Host "[3/3] Starting Next.js Web UI on http://localhost:3000..." -ForegroundColor Green
    $web = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "cd /d `"$PSScriptRoot\web`" && pnpm.cmd dev" -PassThru -NoNewWindow
    $processes += $web

    Write-Host ""
    Write-Host "----------------------------------------------------" -ForegroundColor Yellow
    Write-Host "  All services launched! Press Ctrl+C to stop all.  " -ForegroundColor Yellow
    Write-Host "  - API:      http://localhost:8000" -ForegroundColor White
    Write-Host "  - Swagger:  http://localhost:8000/docs" -ForegroundColor White
    Write-Host "  - Web App:  http://localhost:3000" -ForegroundColor White
    Write-Host "----------------------------------------------------" -ForegroundColor Yellow
    Write-Host ""

    # Keep script alive until interrupted or a process stops
    while ($true) {
        Start-Sleep -Seconds 1
        if ($api.HasExited -or $worker.HasExited -or $web.HasExited) {
            break
        }
    }
}
finally {
    Write-Host "`nStopping all background services..." -ForegroundColor Red
    foreach ($proc in $processes) {
        if ($proc -and -not $proc.HasExited) {
            cmd.exe /c "taskkill /PID $($proc.Id) /T /F >nul 2>&1"
        }
    }
    Write-Host "All services stopped." -ForegroundColor Red
}
