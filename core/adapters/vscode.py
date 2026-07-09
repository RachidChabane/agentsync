"""VS Code Copilot adapter. Code/User/settings.json + a dedicated agentsync hooks file.

VS Code has no MCP/skills surface we manage, and (unlike Claude/Copilot) it reads hooks
from FILES listed in `chat.hookFilesLocations`, not from its settings' own hooks key. So
we give it its own hooks file (determinism gate + session nudge + the user's VS-Code
hooks like `rtk hook copilot`) and point it there — instead of borrowing Claude's hook
file, which would feed it Claude-only hooks (wrong rtk processor, Claude desktop-notify).
"""
from __future__ import annotations

from . import Adapter
from ..targets import Json, Merge
from ..util import Ctx, vscode_user_dir


class VSCode(Adapter):
    name = "vscode"

    def capabilities(self) -> set:
        return {"instructions", "enforcement", "project"}

    def project_targets(self, ctx: Ctx) -> list:
        # Project MCP only (.vscode/mcp.json, top-level key `servers` — VS Code's own
        # dialect). Project instructions (.github/copilot-instructions.md) are owned by
        # the copilot adapter — same file, one owner.
        def entry(s):
            if s["transport"] == "http":
                out = {"type": "http", "url": s["url"]}
                if "auth" in s and "env" in s["auth"]:
                    out["headers"] = {s["auth"]["header"]: "${env:%s}" % s["auth"]["env"]}
                return out
            return {"type": "stdio", "command": s["command"], "args": s["args"]}
        return [Merge(ctx.root / ".vscode" / "mcp.json",
                      owned=[(("servers",), {n: entry(s) for n, s in ctx.servers.items()})],
                      hooks=[], label="mcp")]

    def targets(self, ctx: Ctx) -> list:
        text = self._instructions_text(ctx)
        ov = dict(ctx.overrides.get("vscode", {}))
        user_hookloc = ov.pop("chat.hookFilesLocations", {})  # user's extra (workspace) locations
        user_hooks = ov.pop("hooks", {})                      # user's VS Code hooks (e.g. rtk copilot)
        ov.pop("chat.useCustomAgentHooks", None)              # owned below
        extra_owned = [((k,), v) for k, v in ov.items()]      # remaining passthrough keys

        nudge = str(ctx.enforce_dir / "session-nudge.sh")
        guard = str(ctx.enforce_dir / "guard-commit.sh")
        hooks_file = ctx.root / ".config" / "agentsync" / "vscode-hooks.json"
        vscode_hooks = {"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": f'"{nudge}"'}]}],
            "PreToolUse": [{"hooks": [{"type": "command", "command": f'"{guard}"'}]}],
        } if ctx.enforcement else {}}  # file still carries the user's own VS Code hooks
        for ev, groups in user_hooks.items():                 # merge user hooks (rtk copilot) in
            vscode_hooks["hooks"].setdefault(ev, []).extend(groups)

        # Own the agentsync hooks file location; keep the user's (workspace-relative) ones.
        hookloc = {str(hooks_file): True, **user_hookloc}

        return [
            Json(hooks_file, vscode_hooks, "vscode-hooks"),
            Merge(vscode_user_dir(ctx.root) / "settings.json",
                  owned=[(("github.copilot.chat.codeGeneration.instructions",), [{"text": text}]),
                         (("chat.useCustomAgentHooks",), True),
                         (("chat.hookFilesLocations",), hookloc)] + extra_owned,
                  hooks=[], label="settings"),
        ]
