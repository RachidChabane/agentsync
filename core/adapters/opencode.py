"""OpenCode adapter. ~/.config/opencode/opencode.json (owns the mcp block, the
permission.skill map, and the instructions ref — preserving everything else) plus a
symlinked enforcement plugin.

OpenCode reads instruction files by path, verbatim, so the ref points at one rendered
file (shared text + variant, every `@include` expanded) that this adapter owns."""
from __future__ import annotations

import os
from pathlib import Path

from . import Adapter
from ..targets import File, Link, Merge
from ..util import Ctx, HIDDEN_TIERS

USER_RENDERED_INSTRUCTIONS = Path(".config") / "agentsync" / "opencode-instructions.md"
PROJECT_RENDERED_INSTRUCTIONS = Path(".opencode") / "agentsync-instructions.md"


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

    def _rendered_instructions(self, ctx: Ctx, path: Path, ref) -> tuple:
        """(the opencode.json `instructions` list, the rendered file it points at)."""
        return [ref(path)], File(path, self._instructions_text(ctx), "instructions")

    def project_targets(self, ctx: Ctx) -> list:
        # opencode.json at repo root; instructions as repo-relative paths so the file
        # works on every teammate's checkout.
        ins, rendered = self._rendered_instructions(
            ctx, ctx.root / PROJECT_RENDERED_INSTRUCTIONS, lambda p: os.path.relpath(p, ctx.root))
        return [rendered,
                Merge(ctx.root / "opencode.json",
                      owned=[(("mcp",), {n: mcp_entry(s) for n, s in ctx.servers.items()}),
                             (("instructions",), ins)],
                      hooks=[], label="config")]

    def targets(self, ctx: Ctx) -> list:
        base = ctx.root / ".config" / "opencode"
        servers = {n: mcp_entry(s) for n, s in ctx.servers.items()}
        skill_perms = {"*": "allow"}
        skill_perms.update({s: "deny" for s, t in ctx.tiers_for(self.name).items() if t in HIDDEN_TIERS})
        extra_owned, extra_hooks = self._passthrough(ctx)
        ins, rendered = self._rendered_instructions(ctx, ctx.root / USER_RENDERED_INSTRUCTIONS, str)
        return [
            rendered,
            Merge(base / "opencode.json",
                  owned=[(("mcp",), servers),
                         (("permission", "skill"), skill_perms),
                         (("instructions",), ins)] + extra_owned,
                  hooks=[], extra_hooks=extra_hooks, label="config"),
            *([Link(base / "plugin" / "determinism.js",
                    ctx.enforce_dir / "opencode-plugin.js", "plugin")]
              if ctx.enforcement else []),
        ]
