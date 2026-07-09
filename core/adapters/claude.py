"""Claude Code adapter. ~/.claude/{CLAUDE.md, settings.json, mcp-servers.json}.
User-scope MCP lives in the stateful ~/.claude.json (can't be symlinked) → an artifact
file plus a ClaudeMcp target that imports it via the CLI."""
from __future__ import annotations

from . import Adapter
from ..targets import ClaudeMcp, File, HookSpec, Json, Merge
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
        return {"instructions", "skills", "mcp", "enforcement", "project"}

    def project_targets(self, ctx: Ctx) -> list:
        # Committed, team-shared: CLAUDE.md + .mcp.json (Claude's project-MCP standard).
        # Teammates get env-based headers, not this machine's headersHelper; enforcement
        # stays user-scope — the $HOME hooks already gate every repo.
        def entry(s):
            if s["transport"] == "http":
                out = {"type": "http", "url": s["url"]}
                if "auth" in s and "env" in s["auth"]:
                    out["headers"] = {s["auth"]["header"]: "${%s}" % s["auth"]["env"]}
                return out
            return {"type": "stdio", "command": s["command"], "args": s["args"], "env": {}}
        return [
            File(ctx.root / "CLAUDE.md", self._instructions_text(ctx), "instructions"),
            Merge(ctx.root / ".mcp.json",
                  owned=[(("mcpServers",), {n: entry(s) for n, s in ctx.servers.items()})],
                  hooks=[], label="mcp"),
        ]

    def targets(self, ctx: Ctx) -> list:
        base = ctx.root / ".claude"
        servers = {n: mcp_entry(s) for n, s in ctx.servers.items()}
        overrides = {s: t for s, t in ctx.skills.items() if t != "on"}  # 'on' = omit
        nudge = str(ctx.enforce_dir / "session-nudge.sh")
        guard = str(ctx.enforce_dir / "guard-commit.sh")
        extra_owned, extra_hooks = self._passthrough(ctx)
        return [
            self._instructions(ctx, base / "CLAUDE.md"),
            Json(base / "mcp-servers.json", servers, "mcp"),
            Merge(base / "settings.json",
                  owned=[(("skillOverrides",), overrides)] + extra_owned,
                  hooks=[HookSpec("SessionStart", f'"{nudge}" || true', "session-nudge.sh"),
                         HookSpec("PreToolUse", f'"{guard}"', "guard-commit.sh", matcher="Bash")]
                  if ctx.enforcement else [],
                  extra_hooks=extra_hooks, label="settings"),
            ClaudeMcp(servers, ctx.root),
            *self._skill_links(ctx, base / "skills"),
        ]
