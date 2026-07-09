"""Windsurf adapter. ~/.codeium/windsurf/{memories/global_rules.md, mcp_config.json}.
Remote servers use `serverUrl` (no `type` field). Project scope: AGENTS.md (supported
natively; Windsurf's own project-rules dirs are mid-rebrand under Cognition — the open
standard is the stable target). Note: global_rules.md is capped at 6000 chars by the tool.
"""
from __future__ import annotations

from . import FileHarness


class Windsurf(FileHarness):
    name = "windsurf"
    instructions_path = ".codeium/windsurf/memories/global_rules.md"
    mcp_path = ".codeium/windsurf/mcp_config.json"

    def mcp_entry(self, s: dict) -> dict:
        if s["transport"] == "http":
            out = {"serverUrl": s["url"]}
            if "auth" in s and "env" in s["auth"]:
                out["headers"] = {s["auth"]["header"]: "${%s}" % s["auth"]["env"]}
            return out
        return {"command": s["command"], "args": s["args"]}
