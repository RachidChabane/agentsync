"""GitHub Copilot CLI adapter. ~/.copilot/{copilot-instructions.md, mcp-config.json,
settings.json}. Fail-closed harness; sessionStart can't inject, so the nudge runs on
userPromptSubmitted."""
from __future__ import annotations

from . import Adapter
from ..targets import HookSpec, Json, Link, Merge
from ..util import Ctx, HIDDEN_TIERS


def mcp_entry(s: dict) -> dict:
    if s["transport"] == "http":
        out = {"tools": ["*"], "type": "http", "url": s["url"]}
        if "auth" in s and "env" in s["auth"]:
            out["headers"] = {s["auth"]["header"]: "${%s}" % s["auth"]["env"]}
        return out
    return {"tools": ["*"], "type": "local", "command": s["command"], "args": s["args"]}


class Copilot(Adapter):
    name = "copilot"

    def capabilities(self) -> set:
        return {"instructions", "skills", "mcp", "enforcement"}

    def targets(self, ctx: Ctx) -> list:
        base = ctx.root / ".copilot"
        servers = {"mcpServers": {n: mcp_entry(s) for n, s in ctx.servers.items()}}
        hidden = sorted(s for s, t in ctx.skills.items() if t in HIDDEN_TIERS)
        nudge = str(ctx.enforce_dir / "prompt-context.sh")
        guard = str(ctx.enforce_dir / "guard-commit.sh")
        extra_owned, extra_hooks = self._passthrough(ctx)
        return [
            Link(base / "copilot-instructions.md", ctx.instructions, "instructions"),
            Json(base / "mcp-config.json", servers, "mcp"),
            Merge(base / "settings.json",
                  owned=[(("disabledSkills",), hidden)] + extra_owned,
                  hooks=[HookSpec("userPromptSubmitted", nudge, "prompt-context.sh", key="bash"),
                         HookSpec("preToolUse", guard, "guard-commit.sh", matcher="bash", key="bash")],
                  extra_hooks=extra_hooks, label="settings"),
            *self._skill_links(ctx, base / "skills"),
        ]
