"""Entrypoint script for launching the EMIMIND MCP Server."""

from __future__ import annotations

from services.mcp.server import mcp

if __name__ == "__main__":
    mcp.run()
