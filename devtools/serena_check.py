"""Verify a local Serena MCP connection without changing client configuration."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def check(args):
    home = str(Path(args.cache_home).resolve())
    os.makedirs(home, exist_ok=True)
    if args.uv_bin:
        os.environ["PATH"] = str(Path(args.uv_bin).resolve()) + os.pathsep + os.environ.get("PATH", "")
    # MCP stdio inherits only a small environment allowlist. Use Serena's
    # platform-independent home setting and forward only uv cache controls;
    # never copy the host environment (which may contain API credentials).
    server_env = {"SERENA_HOME": home, "UV_CACHE_DIR": str(Path(home) / "uv-cache")}
    for name in ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_PYTHON_DOWNLOADS"):
        if name in os.environ:
            server_env[name] = os.environ[name]
    boot = "from serena.cli import top_level; top_level()"
    params = StdioServerParameters(command=sys.executable, env=server_env, args=[
        "-c", boot, "start-mcp-server", "--project", str(Path(__file__).resolve().parents[1]),
        "--context", "codex", "--enable-web-dashboard", "false",
        "--open-web-dashboard", "false", "--enable-gui-log-window", "false",
        "--log-level", "ERROR"])
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            for name, arguments in [
                ("get_symbols_overview", {"relative_path": "main.py", "depth": 0}),
                ("find_referencing_symbols", {"name_path": "request_trace", "relative_path": "observability.py"}),
            ]:
                result = await session.call_tool(name, arguments)
                if result.isError:
                    print(json.dumps({"tool": name, "status": "failed"}))
                    return 1
                print(json.dumps({"tool": name, "status": "ok"}))
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-home", required=True)
    parser.add_argument("--uv-bin", help="Directory containing uv/uvx if absent from PATH")
    sys.exit(asyncio.run(check(parser.parse_args())))
