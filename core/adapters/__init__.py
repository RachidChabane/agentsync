"""Harness adapters — the only place per-harness knowledge lives.

Each adapter declares, via `targets()`, *what it manages* in one harness's native files
(instructions, skills, MCP, enforcement). The reconciler interprets those targets for
every verb. Adding a 5th harness = a new module + one line in ADAPTERS; no existing
adapter or the reconciler changes (Open/Closed). `capabilities()` lets the reconciler
degrade gracefully when a harness lacks a surface (e.g. VS Code has no MCP/skills).
"""
from __future__ import annotations

from ..util import Ctx


class Adapter:
    name = ""

    def capabilities(self) -> set:
        """Subset of {"instructions", "skills", "mcp", "enforcement"}."""
        return set()

    def targets(self, ctx: Ctx) -> list:
        raise NotImplementedError

    def _passthrough(self, ctx: Ctx):
        """User's arbitrary settings for this harness (config/overrides.json): scalar/
        object keys owned wholesale, plus optional additive `hooks`."""
        ov = ctx.overrides.get(self.name, {})
        owned = [((k,), v) for k, v in ov.items() if k != "hooks"]
        return owned, ov.get("hooks", {})

    def _skill_links(self, ctx: Ctx, skills_dir):
        from ..targets import Link
        return [Link(skills_dir / name, p, f"skill:{name}")
                for name, p in ctx.skill_paths.items() if p]


from .claude import Claude          # noqa: E402
from .copilot import Copilot        # noqa: E402
from .opencode import OpenCode      # noqa: E402
from .vscode import VSCode          # noqa: E402

ADAPTERS = {a.name: a for a in (Claude(), Copilot(), OpenCode(), VSCode())}
