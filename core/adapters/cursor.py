"""Cursor adapter. User scope is MCP-only: Cursor's global "User Rules" live in its
settings UI (no file to render — honest degradation), MCP in ~/.cursor/mcp.json.
Project scope: AGENTS.md (natively supported) + .cursor/mcp.json. Remote servers are
inferred from `url` — Cursor's schema has no `type` field."""
from __future__ import annotations

from . import FileHarness
from ..util import Ctx


class Cursor(FileHarness):
    name = "cursor"
    mcp_path = ".cursor/mcp.json"

    def mcp_entry(self, s: dict) -> dict:
        if s["transport"] == "http":
            out = {"url": s["url"]}
            if "auth" in s and "env" in s["auth"]:
                out["headers"] = {s["auth"]["header"]: "${%s}" % s["auth"]["env"]}
            return out
        return {"command": s["command"], "args": s["args"]}

    def project_targets(self, ctx: Ctx) -> list:
        return super().project_targets(ctx) + [self._mcp_merge(ctx, ctx.root / ".cursor" / "mcp.json")]
