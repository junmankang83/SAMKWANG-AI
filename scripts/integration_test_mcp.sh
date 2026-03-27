#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/backend/.venv/bin/python"
export PYTHONPATH="${ROOT}/backend"
cd "$ROOT"
"$PY" - <<'PY'
import asyncio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

async def main():
    p = StdioServerParameters(
        command=__import__("sys").executable,
        args=["-m", "mcp_server.mcp_erp_server"],
        cwd=__import__("os").getcwd(),
    )
    async with stdio_client(p) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            r = await session.call_tool("erp_search_items", {"query": "demo", "limit": 1})
            assert not r.isError
            print("MCP integration OK:", r.content[0].text[:120], "...")

asyncio.run(main())
PY
echo "integration_test_mcp.sh: OK"
