#!/usr/bin/env bash

echo "===================================================="
echo "         Stopping EmiMind Dev Services              "
echo "===================================================="

# Detect Windows environment (Git Bash / MSYS / MINGW / CYGWIN)
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" || -n "$WINDIR" ]]; then
    echo "Stopping services on Windows..."

    # Find and terminate processes listening on ports 8000 (FastAPI), 3000 (Next.js), 9000 (MinIO API), and 9001 (MinIO Console)
    for port in 8000 3000 9000 9001; do
        pids=$(netstat -ano 2>/dev/null | grep ":$port " | awk '{print $NF}' | sort -u)
        for pid in $pids; do
            if [[ "$pid" =~ ^[0-9]+$ ]] && [ "$pid" -ne 0 ]; then
                echo "Terminating process on port $port (PID: $pid)..."
                taskkill //PID "$pid" //T //F 2>/dev/null || true
            fi
        done
    done

    # Kill any lingering uvicorn and minio processes
    taskkill //IM uvicorn.exe //T //F 2>/dev/null || true
    taskkill //IM minio.exe //T //F 2>/dev/null || true

    # Kill MCP server (stdio, no listening port — match by command line via wmic)
    mcp_pids=$(wmic process where "name='python.exe' or name='py.exe'" get processid,commandline 2>/dev/null | grep -E "run_mcp_server\.py|services\.mcp\.server" | awk '{print $NF}')
    for pid in $mcp_pids; do
        if [[ "$pid" =~ ^[0-9]+$ ]] && [ "$pid" -ne 0 ]; then
            echo "Terminating MCP server (PID: $pid)..."
            taskkill //PID "$pid" //T //F 2>/dev/null || true
        fi
    done
else
    # Linux / macOS / WSL
    echo "Stopping services on Unix..."

    for port in 8000 3000; do
        pids=$(lsof -ti :$port 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo "Terminating processes on port $port ($pids)..."
            kill -9 $pids 2>/dev/null || true
        fi
    done

    # Kill background arq / uvicorn / mcp by process signature
    pkill -f "arq services.ingest.worker" 2>/dev/null || true
    pkill -f "uvicorn services.api.main" 2>/dev/null || true
    pkill -f "scripts/run_mcp_server.py" 2>/dev/null || true
    pkill -f "services.mcp.server" 2>/dev/null || true
fi

echo "===================================================="
echo "  All EmiMind application services have stopped.    "
echo "===================================================="
