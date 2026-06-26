"""VS Code Copilot adapter. Code/User/settings.json. VS Code has no MCP/skills surface
we manage here (capabilities() reflects that), so it only inlines the instructions (no
external user-scope file ref is allowed) and reuses Claude's hooks via
chat.hookFilesLocations — so the determinism gate requires the Claude adapter enabled."""
from __future__ import annotations

from . import Adapter
from ..util import Ctx, Report, merge_json, vscode_user_dir


class VSCode(Adapter):
    name = "vscode"

    def capabilities(self) -> set:
        return {"instructions", "enforcement"}

    def apply(self, ctx: Ctx) -> Report:
        rep = Report(self.name)
        settings = vscode_user_dir(ctx.root) / "settings.json"
        text = ctx.instructions.read_text()

        def mutate(d: dict):
            d["github.copilot.chat.codeGeneration.instructions"] = [{"text": text}]
            d["chat.useCustomAgentHooks"] = True
            d.setdefault("chat.hookFilesLocations", {})["~/.claude/settings.json"] = True

        merge_json(settings, mutate, ctx, rep, "settings")
        return rep
