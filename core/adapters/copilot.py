"""GitHub Copilot CLI adapter. ~/.copilot/{copilot-instructions.md, mcp-config.json,
settings.json}. Fail-closed harness, so its commit gate uses the same guard (exits 0/2
only). sessionStart can't inject context, so the nudge runs on userPromptSubmitted."""
from __future__ import annotations

from . import Adapter
from ..util import (Ctx, HIDDEN_TIERS, Report, ensure_command_hook, merge_json,
                    symlink, write_json)


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

    def apply(self, ctx: Ctx) -> Report:
        rep = Report(self.name)
        base = ctx.root / ".copilot"

        symlink(base / "copilot-instructions.md", ctx.instructions, ctx, rep, "instructions")
        write_json(base / "mcp-config.json",
                   {"mcpServers": {n: mcp_entry(s) for n, s in ctx.servers.items()}},
                   ctx, rep, "mcp")

        hidden = sorted(s for s, t in ctx.skills.items() if t in HIDDEN_TIERS)
        nudge = str(ctx.enforce_dir / "prompt-context.sh")
        guard = str(ctx.enforce_dir / "guard-commit.sh")

        def mutate(d: dict):
            d["disabledSkills"] = hidden
            hooks = d.setdefault("hooks", {})
            ensure_command_hook(hooks, "userPromptSubmitted", nudge, key="bash")
            ensure_command_hook(hooks, "preToolUse", guard, matcher="bash", key="bash")

        merge_json(base / "settings.json", mutate, ctx, rep, "settings")
        return rep
