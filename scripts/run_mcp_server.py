"""Entrypoint script for launching the EMIMIND MCP Server."""

from __future__ import annotations

import sys
from services.mcp.server import mcp

if __name__ == "__main__":
    mcp.run()
