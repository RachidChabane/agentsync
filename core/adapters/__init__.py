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
        """Subset of {"instructions", "skills", "mcp", "enforcement", "project"}."""
        return set()

    def targets(self, ctx: Ctx) -> list:
        raise NotImplementedError

    def project_targets(self, ctx: Ctx) -> list:
        """Targets rendered into a repo (`--project`): committed files a team shares.
        Empty = the harness has no project-scope surface (graceful degradation)."""
        return []

    def _variant(self, ctx: Ctx):
        """Optional per-harness instruction variant: config/instructions.<name>.md is
        appended to the shared instructions for this harness only."""
        p = ctx.config / f"instructions.{self.name}.md"
        return p if p.exists() else None

    def _instructions_text(self, ctx: Ctx) -> str:
        var = self._variant(ctx)
        base = ctx.instructions.read_text()
        return base.rstrip() + "\n\n" + var.read_text() if var else base

    def _instructions(self, ctx: Ctx, dest):
        """Symlink the shared instructions — or, when a variant exists, own a rendered
        base+variant file (a symlink can't express the concatenation)."""
        from ..targets import File, Link
        if self._variant(ctx):
            return File(dest, self._instructions_text(ctx), "instructions")
        return Link(dest, ctx.instructions, "instructions")

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


class FileHarness(Adapter):
    """Generic base for the common harness shape: one instructions file + one MCP JSON,
    no hook/skill surface. A subclass is just paths + an MCP entry renderer (~10 lines);
    leave `mcp_path` empty for instructions-only harnesses."""
    instructions_path = ""  # relative to root
    mcp_path = ""           # relative to root; "" = no MCP surface
    mcp_key = "mcpServers"  # top-level key in the MCP file

    def mcp_entry(self, s: dict) -> dict:
        raise NotImplementedError

    def capabilities(self) -> set:
        return ({"instructions"} if self.instructions_path else set()) \
            | ({"mcp"} if self.mcp_path else set()) | {"project"}

    def targets(self, ctx: Ctx) -> list:
        out: list = [self._instructions(ctx, ctx.root / self.instructions_path)] \
            if self.instructions_path else []
        if self.mcp_path:
            out.append(self._mcp_merge(ctx, ctx.root / self.mcp_path))
        return out

    def _mcp_merge(self, ctx: Ctx, path):
        """Own only the servers key in the harness's (user-shared) MCP file."""
        from ..targets import Merge
        servers = {n: self.mcp_entry(s) for n, s in ctx.servers.items()}
        return Merge(path, owned=[((self.mcp_key,), servers)], hooks=[], label="mcp")

    def project_targets(self, ctx: Ctx) -> list:
        # All FileHarness tools read a repo-root AGENTS.md (the open standard). Shared
        # base text only — several adapters may own this one file, so no per-harness
        # variants here (they'd fight over the content).
        from ..targets import File
        return [File(ctx.root / "AGENTS.md", ctx.instructions.read_text(), "instructions")]


from .claude import Claude          # noqa: E402
from .cline import Cline            # noqa: E402
from .copilot import Copilot        # noqa: E402
from .cursor import Cursor          # noqa: E402
from .opencode import OpenCode      # noqa: E402
from .vscode import VSCode          # noqa: E402
from .windsurf import Windsurf      # noqa: E402
from .zed import Zed                # noqa: E402

ADAPTERS = {a.name: a for a in (Claude(), Copilot(), OpenCode(), VSCode(),
                                Cursor(), Windsurf(), Zed(), Cline())}
