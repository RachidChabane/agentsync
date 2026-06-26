"""VS Code Copilot adapter. Code/User/settings.json. No MCP/skills surface we manage
here (capabilities() reflects that) — it inlines the instructions (no external user-scope
file ref allowed) and reuses Claude's hooks via chat.hookFilesLocations, so its
determinism gate requires the Claude adapter enabled."""
from __future__ import annotations

from . import Adapter
from ..targets import Merge
from ..util import Ctx, vscode_user_dir


class VSCode(Adapter):
    name = "vscode"

    def capabilities(self) -> set:
        return {"instructions", "enforcement"}

    def targets(self, ctx: Ctx) -> list:
        text = ctx.instructions.read_text()
        extra_owned, extra_hooks = self._passthrough(ctx)
        return [
            Merge(vscode_user_dir(ctx.root) / "settings.json",
                  owned=[(("github.copilot.chat.codeGeneration.instructions",), [{"text": text}]),
                         (("chat.useCustomAgentHooks",), True),
                         (("chat.hookFilesLocations", "~/.claude/settings.json"), True)] + extra_owned,
                  hooks=[], extra_hooks=extra_hooks, label="settings"),
        ]
