"""OpenCode adapter. ~/.config/opencode/opencode.json (mcp + skill permissions +
instructions) and a symlinked enforcement plugin. Enforcement is a JS plugin (OpenCode
has no shell-hook surface); the nudge degrades safely if experimental hooks change."""
from __future__ import annotations

from . import Adapter
from ..util import Ctx, HIDDEN_TIERS, Report, merge_json, symlink


def mcp_entry(s: dict) -> dict:
    enabled = s.get("opencode", {}).get("enabled", True)
    if s["transport"] == "http":
        out = {"type": "remote", "url": s["url"]}
        if "auth" in s and "env" in s["auth"]:
            out["headers"] = {s["auth"]["header"]: "{env:%s}" % s["auth"]["env"]}
        out["enabled"] = enabled
        return out
    return {"type": "local", "command": [s["command"], *s["args"]], "enabled": enabled}


class OpenCode(Adapter):
    name = "opencode"

    def capabilities(self) -> set:
        return {"instructions", "skills", "mcp", "enforcement"}

    def apply(self, ctx: Ctx) -> Report:
        rep = Report(self.name)
        base = ctx.root / ".config" / "opencode"

        skill_perms = {"*": "allow"}
        skill_perms.update({s: "deny" for s, t in ctx.skills.items() if t in HIDDEN_TIERS})

        def mutate(d: dict):
            d["mcp"] = {n: mcp_entry(s) for n, s in ctx.servers.items()}
            d.setdefault("permission", {})["skill"] = skill_perms
            d["instructions"] = [str(ctx.instructions)]

        merge_json(base / "opencode.json", mutate, ctx, rep, "config")
        symlink(base / "plugin" / "determinism.js",
                ctx.enforce_dir / "opencode-plugin.js", ctx, rep, "plugin")
        return rep
