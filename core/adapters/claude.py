"""Claude Code adapter. ~/.claude/{CLAUDE.md, settings.json, mcp-servers.json}.
User-scope MCP lives in the stateful ~/.claude.json (can't be symlinked) → an artifact
file plus a ClaudeMcp target that imports it via the CLI."""
from __future__ import annotations

from . import Adapter
from ..targets import ClaudeMcp, HookSpec, Json, Link, Merge
from ..util import Ctx


def mcp_entry(s: dict) -> dict:
    if s["transport"] == "http":
        out = {"type": "http", "url": s["url"]}
        if "auth" in s and "headersHelper" in s["auth"]:
            out["headersHelper"] = s["auth"]["headersHelper"]
        return out
    return {"type": "stdio", "command": s["command"], "args": s["args"], "env": {}}


class Claude(Adapter):
    name = "claude"

    def capabilities(self) -> set:
        return {"instructions", "skills", "mcp", "enforcement"}

    def targets(self, ctx: Ctx) -> list:
        base = ctx.root / ".claude"
        servers = {n: mcp_entry(s) for n, s in ctx.servers.items()}
        overrides = {s: t for s, t in ctx.skills.items() if t != "on"}  # 'on' = omit
        nudge = str(ctx.enforce_dir / "session-nudge.sh")
        guard = str(ctx.enforce_dir / "guard-commit.sh")
        extra_owned, extra_hooks = self._passthrough(ctx)
        return [
            Link(base / "CLAUDE.md", ctx.instructions, "instructions"),
            Json(base / "mcp-servers.json", servers, "mcp"),
            Merge(base / "settings.json",
                  owned=[(("skillOverrides",), overrides)] + extra_owned,
                  hooks=[HookSpec("SessionStart", f'"{nudge}" || true', "session-nudge.sh"),
                         HookSpec("PreToolUse", f'"{guard}"', "guard-commit.sh", matcher="Bash")],
                  extra_hooks=extra_hooks, label="settings"),
            ClaudeMcp(servers, ctx.root),
            *self._skill_links(ctx, base / "skills"),
        ]
