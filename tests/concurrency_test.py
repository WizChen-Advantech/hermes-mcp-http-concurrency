"""Three agent threads call one MCP tool at once, through Hermes's own code path.

    python concurrency_test.py <hermes source dir> <http|stdio> <port> <seconds> <label> [plugin]

With "plugin" the plugin is loaded the way the gateway loads it: from
$HERMES_HOME/plugins, enabled in config.yaml, by discover_plugins().
"""

import json
import os
import sys
import threading
import time

hermes, transport, port, seconds, label = sys.argv[1:6]
use_plugin = len(sys.argv) > 6 and sys.argv[6] == "plugin"
seconds = float(seconds)
sys.path.insert(0, hermes)

from tools import mcp_tool as m  # noqa: E402 - the Hermes tree is chosen on the command line

if use_plugin:
    from hermes_cli.plugins import discover_plugins  # noqa: E402

    discover_plugins()

m._ensure_mcp_loop()
here = os.path.dirname(os.path.abspath(__file__))
if transport == "http":
    config = {"url": f"http://127.0.0.1:{port}/mcp", "timeout": 60}
else:
    config = {"command": sys.executable, "args": [os.path.join(here, "slow_server.py"), "stdio"],
              "timeout": 60}
server = m._run_on_mcp_loop(m._connect_server("t", config), timeout=30)
with m._lock:
    m._servers["t"] = server
handler = m._make_tool_handler("t", "slow", 60)
results = {}


def call(who):
    started = time.time()
    out = handler({"seconds": seconds, "who": who})
    results[who] = (time.time() - started, out)


started = time.time()
threads = [threading.Thread(target=call, args=(f"session{i}",)) for i in (1, 2, 3)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()
for who, (took, out) in sorted(results.items()):
    print(f"[{label}] {who}: {took:.1f}s  {json.loads(out).get('result')}")
print(f"[{label}] lock: {type(server._rpc_lock).__name__}; "
      f"3 calls of {seconds:.0f}s took {time.time() - started:.1f}s")
os._exit(0)
