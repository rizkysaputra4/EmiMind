# EmiMind Services Stopper for Windows PowerShell
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "         Stopping EmiMind Dev Services              " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

# Stop processes listening on port 8000 (FastAPI), 3000 (Next.js), 9000 (MinIO API), and 9001 (MinIO Console)
$ports = @(8000, 3000, 9000, 9001)

foreach ($port in $ports) {
    try {
        $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if ($connections) {
            $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
            foreach ($pidToKill in $pids) {
                if ($pidToKill -gt 0) {
                    Write-Host "Terminating process on port $port (PID: $pidToKill)..." -ForegroundColor Yellow
                    cmd.exe /c "taskkill /PID $pidToKill /T /F >nul 2>&1"
                }
            }
        }
    } catch {
        # Fallback using netstat
        $netstatOutput = netstat -ano | Select-String ":$port\s"
        foreach ($line in $netstatOutput) {
            $parts = $line.ToString().Trim() -split '\s+'
            $pidToKill = $parts[-1]
            if ($pidToKill -match '^\d+$' -and [int]$pidToKill -gt 0) {
                Write-Host "Terminating process on port $port (PID: $pidToKill)..." -ForegroundColor Yellow
                cmd.exe /c "taskkill /PID $pidToKill /T /F >nul 2>&1"
            }
        }
    }
}

# Terminate any dangling uvicorn and minio processes
Get-Process -Name "uvicorn", "minio" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# Terminate MCP server (stdio, no listening port — match by command line)
Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'py.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'run_mcp_server\.py|services\.mcp\.server' } |
    ForEach-Object {
        Write-Host "Terminating MCP server (PID: $($_.ProcessId))..." -ForegroundColor Yellow
        cmd.exe /c "taskkill /PID $($_.ProcessId) /T /F >nul 2>&1"
    }

Write-Host "====================================================" -ForegroundColor Green
Write-Host "  All EmiMind application services have stopped.    " -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Green
