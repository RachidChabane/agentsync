"""Cline adapter. Global rules are a directory of markdown files (~/Documents/Cline/Rules
— we link one agentsync-owned file into it); MCP in ~/.cline/mcp.json. Remote servers
need Cline's camelCase `"type": "streamableHttp"`. Project scope: AGENTS.md (supported
natively, preferred over .clinerules/)."""
from __future__ import annotations

from . import FileHarness


class Cline(FileHarness):
    name = "cline"
    instructions_path = "Documents/Cline/Rules/agentsync.md"
    mcp_path = ".cline/mcp.json"

    def mcp_entry(self, s: dict) -> dict:
        if s["transport"] == "http":
            out = {"type": "streamableHttp", "url": s["url"]}
            if "auth" in s and "env" in s["auth"]:
                out["headers"] = {s["auth"]["header"]: "${%s}" % s["auth"]["env"]}
            return out
        return {"command": s["command"], "args": s["args"]}
