"""Claude Code adapter. ~/.claude/{CLAUDE.md, settings.json, mcp-servers.json}.

Note: Claude's user-scope MCP lives in the stateful ~/.claude.json and can't be
symlinked, so we render an mcp-servers.json artifact; the reconciler imports it via the
`claude` CLI as a separate, opt-in side step (never in --check or a sandbox).
"""
from __future__ import annotations

from . import Adapter
from ..util import Ctx, Report, ensure_command_hook, merge_json, symlink, write_json


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

    def apply(self, ctx: Ctx) -> Report:
        rep = Report(self.name)
        base = ctx.root / ".claude"

        symlink(base / "CLAUDE.md", ctx.instructions, ctx, rep, "instructions")
        write_json(base / "mcp-servers.json",
                   {n: mcp_entry(s) for n, s in ctx.servers.items()}, ctx, rep, "mcp")

        overrides = {s: t for s, t in ctx.skills.items() if t != "on"}  # 'on' = omit
        nudge = str(ctx.enforce_dir / "session-nudge.sh")
        guard = str(ctx.enforce_dir / "guard-commit.sh")

        def mutate(d: dict):
            d["skillOverrides"] = overrides
            hooks = d.setdefault("hooks", {})
            ensure_command_hook(hooks, "SessionStart", f'"{nudge}" || true')
            ensure_command_hook(hooks, "PreToolUse", f'"{guard}"', matcher="Bash")

        merge_json(base / "settings.json", mutate, ctx, rep, "settings")
        return rep
