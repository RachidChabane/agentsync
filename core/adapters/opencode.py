"""OpenCode adapter. ~/.config/opencode/opencode.json (owns the mcp block, the
permission.skill map, and the instructions ref — preserving everything else) plus a
symlinked enforcement plugin."""
from __future__ import annotations

from . import Adapter
from ..targets import Link, Merge
from ..util import Ctx, HIDDEN_TIERS


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
        return {"instructions", "skills", "mcp", "enforcement", "project"}

    def project_targets(self, ctx: Ctx) -> list:
        # opencode.json at repo root; instructions as repo-relative paths so the file
        # works on every teammate's checkout.
        import os
        ins = [os.path.relpath(ctx.instructions, ctx.root)]
        if (v := self._variant(ctx)):
            ins.append(os.path.relpath(v, ctx.root))
        return [Merge(ctx.root / "opencode.json",
                      owned=[(("mcp",), {n: mcp_entry(s) for n, s in ctx.servers.items()}),
                             (("instructions",), ins)],
                      hooks=[], label="config")]

    def targets(self, ctx: Ctx) -> list:
        base = ctx.root / ".config" / "opencode"
        servers = {n: mcp_entry(s) for n, s in ctx.servers.items()}
        skill_perms = {"*": "allow"}
        skill_perms.update({s: "deny" for s, t in ctx.skills.items() if t in HIDDEN_TIERS})
        extra_owned, extra_hooks = self._passthrough(ctx)
        return [
            Merge(base / "opencode.json",
                  owned=[(("mcp",), servers),
                         (("permission", "skill"), skill_perms),
                         (("instructions",), [str(ctx.instructions)]
                          + ([str(v)] if (v := self._variant(ctx)) else []))] + extra_owned,
                  hooks=[], extra_hooks=extra_hooks, label="config"),
            *([Link(base / "plugin" / "determinism.js",
                    ctx.enforce_dir / "opencode-plugin.js", "plugin")]
              if ctx.enforcement else []),
        ]
