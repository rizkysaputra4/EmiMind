#!/usr/bin/env bash

set -e

echo "===================================================="
echo "  Starting EmiMind Full-Stack Development Services  "
echo "===================================================="

# Check backing infrastructure ports
check_port() {
    local port=$1
    if nc -z 127.0.0.1 "$port" 2>/dev/null || (echo > /dev/tcp/127.0.0.1/"$port") 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Auto-start MinIO if binary is installed and port 9000 is not running
if ! check_port 9000 && command -v minio &>/dev/null; then
    echo "Auto-starting MinIO server (:9000)..."
    mkdir -p minio-data
    MINIO_ROOT_USER=minioadmin MINIO_ROOT_PASSWORD=minioadmin minio server minio-data --console-address ":9001" --address ":9000" &
    sleep 2
fi

echo ""
echo "Checking infrastructure services:"
check_port 5432 && echo "  - PostgreSQL (:5432) : [OK]" || echo "  - PostgreSQL (:5432) : [NOT RUNNING]"
check_port 6379 && echo "  - Redis      (:6379) : [OK]" || echo "  - Redis      (:6379) : [NOT RUNNING]"
check_port 9000 && echo "  - MinIO      (:9000) : [OK]" || echo "  - MinIO      (:9000) : [NOT RUNNING]"
echo ""

# Trap SIGINT, SIGTERM, and EXIT to gracefully stop all background jobs
cleanup() {
    echo ""
    echo "Shutting down all services..."
    kill $(jobs -p) 2>/dev/null || true
    wait 2>/dev/null || true
    echo "All services stopped."
}
trap cleanup SIGINT SIGTERM EXIT

# 1. FastAPI API Server
echo "[1/4] Starting FastAPI Backend on http://localhost:8000..."
uv run uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000 &

# 2. Background arq Ingestion Worker
echo "[2/4] Starting arq Background Worker..."
uv run arq services.ingest.worker.WorkerSettings &

# 3. Next.js Web Frontend
echo "[3/4] Starting Next.js Web UI on http://localhost:3000..."
(cd web && pnpm dev) &

# 4. MCP Server (stdio — spawned per-client; will exit immediately without a peer)
echo "[4/4] Starting MCP Server (stdio; scripts/run_mcp_server.py)..."
uv run python scripts/run_mcp_server.py &

echo ""
echo "----------------------------------------------------"
echo "  All services running! Press Ctrl+C to stop all.   "
echo "  - API:      http://localhost:8000"
echo "  - Swagger:  http://localhost:8000/docs"
echo "  - Web App:  http://localhost:3000"
echo "  - MCP:      stdio (scripts/run_mcp_server.py)"
echo "----------------------------------------------------"
echo ""

# Wait for all child processes
wait
