# hermes-mcp-http-concurrency

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that lets MCP tool calls
to **HTTP** servers run in parallel.

## Why

Hermes keeps one connection per MCP server and gives it one `asyncio.Lock`
(`MCPServerTask._rpc_lock`), held for the whole `tools/call`. In the gateway, every
session shares that server, so one user's 60-second tool call makes every other user's
tool calls wait their turn. The lock is there for stdio, where requests share a single
JSON-RPC stream; Streamable HTTP gives each request its own id, so they need not queue.

This plugin swaps each server's lock for one that **still locks for stdio** and does
nothing for HTTP. It is applied to servers connected later and to servers already
connected when the plugin loads.

## Measured (Hermes 0.13.0, `498bfc7bc1`, mcp SDK 1.28.1)

Three threads calling one 5-second tool at once, through Hermes's own tool handler,
with the plugin loaded the way the gateway loads it (`$HERMES_HOME/plugins`, enabled in
`config.yaml`, `discover_plugins()`):

| | per call | total |
|---|---|---|
| HTTP, without plugin | 5 / 10 / 15 s | 15.0 s |
| HTTP, with plugin | 5 / 5 / 5 s | 5.0 s |
| stdio, with plugin (lock kept) | 5 / 10 / 15 s | 15.1 s |
| HTTP, plugin applied after the server connected | | 5.0 s |

Each call got its own result.

## Install

Dashboard: **Plugins → Install** with `WizChen-Advantech/hermes-mcp-http-concurrency`,
enable it, then restart the gateway. Or on the host:

```bash
hermes plugins install WizChen-Advantech/hermes-mcp-http-concurrency
hermes plugins enable mcp-http-concurrency
```

The gateway log then shows
`mcp-http-concurrency: HTTP MCP calls run in parallel (already connected: ...)`.

To undo, disable the plugin and restart the gateway.

## Safety

- Only HTTP servers change; stdio servers keep their lock.
- If a Hermes release no longer has `tools.mcp_tool.MCPServerTask._is_http`, the plugin
  logs one warning and changes nothing (`tests/test_fallback.py`).
- Your MCP server must handle concurrent requests. Servers built on the MCP SDK's
  Streamable HTTP transport do.

## Tests

```bash
python tests/test_fallback.py
python tests/slow_server.py http 8766 &
HERMES_HOME=<dir with plugins/mcp-http-concurrency and plugins.enabled in config.yaml> \
  python tests/concurrency_test.py <hermes source> http 8766 5 with-plugin plugin
```

## License

MIT
