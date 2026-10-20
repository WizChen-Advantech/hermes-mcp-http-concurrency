"""The plugin changes nothing when Hermes no longer has what it patches.

    python tests/test_fallback.py
"""

import importlib.util
import os
import sys
import types

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("plugin", os.path.join(here, "..", "__init__.py"))
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

# 1. No tools.mcp_tool at all.
sys.modules.pop("tools", None)
sys.modules.pop("tools.mcp_tool", None)
assert plugin.apply() is False

# 2. A Hermes whose MCPServerTask has no _is_http: the class must be left alone.
tools = types.ModuleType("tools")
mcp_tool = types.ModuleType("tools.mcp_tool")


class MCPServerTask:
    def __init__(self, name):
        self._rpc_lock = object()


mcp_tool.MCPServerTask = MCPServerTask
tools.mcp_tool = mcp_tool
sys.modules["tools"], sys.modules["tools.mcp_tool"] = tools, mcp_tool
original_init = MCPServerTask.__init__
assert plugin.apply() is False
assert MCPServerTask.__init__ is original_init
print("fallback: ok")
