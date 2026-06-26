"""Harness adapters — the only place per-harness knowledge lives.

Each adapter renders the shared config (instructions, skills, MCP, enforcement hooks)
into one harness's native files. The reconciler (agentsync.py) is closed for
modification: adding a 5th harness means writing a new module here and adding one line
to ADAPTERS — no existing adapter or the reconciler changes (Open/Closed).

An adapter declares `capabilities()` so the reconciler degrades gracefully when a
harness can't do something (e.g. VS Code has no MCP/skills surface) instead of failing.
"""
from __future__ import annotations

from ..util import Ctx, Report


class Adapter:
    name = ""

    def capabilities(self) -> set:
        """Subset of {"instructions", "skills", "mcp", "enforcement"}."""
        return set()

    def apply(self, ctx: Ctx) -> Report:
        raise NotImplementedError


from .claude import Claude          # noqa: E402
from .copilot import Copilot        # noqa: E402
from .opencode import OpenCode      # noqa: E402
from .vscode import VSCode          # noqa: E402

ADAPTERS = {a.name: a for a in (Claude(), Copilot(), OpenCode(), VSCode())}
