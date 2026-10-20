"""An MCP server with one sleeping tool: `slow_server.py http <port>` or `slow_server.py stdio`."""

import asyncio
import sys
import time

from mcp.server.fastmcp import FastMCP

transport = sys.argv[1]
port = int(sys.argv[2]) if transport == "http" else 0
mcp = FastMCP("slow", host="127.0.0.1", port=port)


@mcp.tool()
async def slow(seconds: float = 5, who: str = "") -> str:
    print(f"start {who} {time.time():.2f}", file=sys.stderr, flush=True)
    await asyncio.sleep(seconds)
    print(f"end   {who} {time.time():.2f}", file=sys.stderr, flush=True)
    return f"{who} slept {seconds}s"


mcp.run(transport="streamable-http" if transport == "http" else "stdio")
