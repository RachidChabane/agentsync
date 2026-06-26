#!/usr/bin/env python3
"""End-to-end check of the reconciler against a sandbox root (never touches $HOME).

Runs `apply` into a temp dir, asserts each harness's native files, then asserts
idempotency (verify == clean) and drift detection (tamper -> verify fails). Plain
asserts, no framework. Run from the repo root: `python3 tests/test_apply.py`.
"""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import agentsync  # noqa: E402

CFG = REPO / "config.example"


def run(*args) -> int:
    return agentsync.main(list(args))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        common = ["--root", str(root), "--config", str(CFG), "--no-mcp-import"]

        assert run("apply", *common) == 0, "apply failed"

        # Claude
        claude_mcp = json.loads((root / ".claude/mcp-servers.json").read_text())
        assert claude_mcp["context7"] == {"type": "http", "url": "https://mcp.context7.com/mcp"}
        assert claude_mcp["example-authed-server"]["headersHelper"] == "~/.config/example/headers.sh"
        cs = json.loads((root / ".claude/settings.json").read_text())
        assert cs["skillOverrides"]["example-domain-skill"] == "user-invocable-only"
        assert "example-every-session-skill" not in cs["skillOverrides"], "tier 'on' must be omitted"
        cmds = [h["command"] for g in cs["hooks"]["PreToolUse"] for h in g["hooks"]]
        assert any("guard-commit.sh" in c for c in cmds), "commit gate not wired"
        assert (root / ".claude/CLAUDE.md").is_symlink()

        # Copilot
        cop = json.loads((root / ".copilot/settings.json").read_text())
        assert cop["disabledSkills"] == ["example-domain-skill"], cop["disabledSkills"]
        cop_mcp = json.loads((root / ".copilot/mcp-config.json").read_text())
        assert cop_mcp["mcpServers"]["context7"]["type"] == "http"
        bashes = [h["bash"] for h in cop["hooks"]["preToolUse"]]
        assert any("guard-commit.sh" in b for b in bashes)

        # OpenCode
        oc = json.loads((root / ".config/opencode/opencode.json").read_text())
        assert oc["permission"]["skill"] == {"*": "allow", "example-domain-skill": "deny"}
        assert oc["mcp"]["example-authed-server"]["enabled"] is False, "per-harness opt-out ignored"
        assert oc["mcp"]["context7"]["type"] == "remote"
        assert (root / ".config/opencode/plugin/determinism.js").is_symlink()

        # VS Code (instructions inline; no MCP surface)
        from core.util import vscode_user_dir
        vs = json.loads((vscode_user_dir(root) / "settings.json").read_text())
        assert vs["github.copilot.chat.codeGeneration.instructions"][0]["text"].startswith("# Global")

        # Idempotency + drift
        assert run("verify", *common) == 0, "verify should be clean right after apply"
        cs["hooks"]["PreToolUse"] = []           # tamper: drop the gate
        (root / ".claude/settings.json").write_text(json.dumps(cs))
        assert run("verify", *common) == 1, "verify should detect the dropped gate"
        assert run("apply", *common) == 0 and run("verify", *common) == 0, "apply should re-converge"

    print("\ntest_apply: PASS")


if __name__ == "__main__":
    main()
