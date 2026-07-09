#!/usr/bin/env python3
"""End-to-end check of the reconciler against a sandbox root (never touches $HOME).

Self-contained fixture (not config.example) so it can exercise auth, stdio, per-harness
opt-out and every skill tier regardless of what the example ships. Covers: rendering per
harness, idempotency, drift detection, merge-PRESERVATION (unrelated user keys survive),
and pruning of a removed MCP server. Plain asserts. Run from repo root.
"""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import agentsync          # noqa: E402
from core.util import vscode_user_dir  # noqa: E402

FIXTURE_MCP = {"servers": {
    "context7": {"transport": "http", "url": "https://mcp.context7.com/mcp"},
    "db": {"transport": "stdio", "command": "npx", "args": ["-y", "db-mcp@latest"]},
    "secret": {"transport": "http", "url": "https://api.x.com/mcp",
               "auth": {"header": "x-key", "headersHelper": "~/.config/x/h.sh", "env": "X_KEY"},
               "opencode": {"enabled": False}},
}}
FIXTURE_SKILLS = {"skills": {"always": "on", "generic": "name-only",
                             "domain": "user-invocable-only", "dead": "off"}}


def write_config(cfg: Path):
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "instructions.md").write_text("# Global\nbe deterministic\n")
    (cfg / "mcp.json").write_text(json.dumps(FIXTURE_MCP))
    (cfg / "skills.json").write_text(json.dumps(FIXTURE_SKILLS))
    (cfg / "profile.json").write_text(json.dumps(
        {"harnesses": ["claude", "copilot", "opencode", "vscode"]}))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg = Path(tmp) / "home", Path(tmp) / "cfg"
        write_config(cfg)
        common = ["--root", str(root), "--config", str(cfg), "--no-mcp-import"]

        # Pre-seed live files with UNRELATED user content the tool must preserve.
        (root / ".claude").mkdir(parents=True)
        (root / ".claude/settings.json").write_text(json.dumps({
            "statusLine": {"type": "command", "command": "mine"},          # unrelated key
            "hooks": {"PreToolUse": [{"matcher": "AskUserQuestion",
                                      "hooks": [{"type": "command", "command": "notify"}]}]},
        }))
        (root / ".config/opencode").mkdir(parents=True)
        (root / ".config/opencode/opencode.json").write_text(json.dumps({
            "theme": "dark", "permission": {"bash": "ask"}}))            # unrelated keys

        assert agentsync.main(["apply", *common]) == 0, "apply failed"

        # --- rendering ---
        cm = json.loads((root / ".claude/mcp-servers.json").read_text())
        assert cm["context7"] == {"type": "http", "url": "https://mcp.context7.com/mcp"}
        assert cm["secret"]["headersHelper"] == "~/.config/x/h.sh"
        cs = json.loads((root / ".claude/settings.json").read_text())
        assert cs["skillOverrides"] == {"generic": "name-only", "domain": "user-invocable-only",
                                        "dead": "off"}, "tier 'on' must be omitted"
        gate = [h["command"] for g in cs["hooks"]["PreToolUse"] for h in g["hooks"]]
        assert any("guard-commit.sh" in c for c in gate)

        cop = json.loads((root / ".copilot/settings.json").read_text())
        assert cop["disabledSkills"] == ["dead", "domain"], cop["disabledSkills"]
        assert json.loads((root / ".copilot/mcp-config.json").read_text())["mcpServers"]["secret"]["headers"] \
            == {"x-key": "${X_KEY}"}

        oc = json.loads((root / ".config/opencode/opencode.json").read_text())
        assert oc["permission"]["skill"] == {"*": "allow", "domain": "deny", "dead": "deny"}
        assert oc["mcp"]["secret"]["enabled"] is False, "per-harness opt-out ignored"
        assert oc["mcp"]["db"]["command"] == ["npx", "-y", "db-mcp@latest"]
        assert (root / ".config/opencode/plugin/determinism.js").is_symlink()

        vs = json.loads((vscode_user_dir(root) / "settings.json").read_text())
        assert vs["github.copilot.chat.codeGeneration.instructions"][0]["text"].startswith("# Global")

        # --- merge PRESERVATION: unrelated user content survives ---
        assert cs["statusLine"] == {"type": "command", "command": "mine"}, "clobbered user key!"
        assert any(g.get("matcher") == "AskUserQuestion" for g in cs["hooks"]["PreToolUse"]), \
            "clobbered user's hook group!"
        assert oc["theme"] == "dark" and oc["permission"]["bash"] == "ask", "clobbered opencode keys!"

        # --- idempotency + drift ---
        assert agentsync.main(["verify", *common]) == 0, "verify dirty right after apply"
        cs["hooks"]["PreToolUse"] = []
        (root / ".claude/settings.json").write_text(json.dumps(cs))
        assert agentsync.main(["verify", *common]) == 1, "drift not detected"
        assert agentsync.main(["apply", *common]) == 0
        assert agentsync.main(["verify", *common]) == 0, "did not re-converge"

        # --- MCP prune: drop a server, artifact no longer lists it ---
        FIXTURE_MCP["servers"].pop("db")
        (cfg / "mcp.json").write_text(json.dumps(FIXTURE_MCP))
        assert agentsync.main(["apply", *common]) == 0
        assert "db" not in json.loads((root / ".claude/mcp-servers.json").read_text())

    enforcement_off()
    print("\ntest_apply: PASS")


def enforcement_off():
    """profile {"enforcement": false} => config sync only: no gate/nudge hooks anywhere,
    no OpenCode plugin — while instructions/MCP/skills still render."""
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg = Path(tmp) / "home", Path(tmp) / "cfg"
        write_config(cfg)
        (cfg / "profile.json").write_text(json.dumps(
            {"harnesses": ["claude", "copilot", "opencode", "vscode"], "enforcement": False}))
        common = ["--root", str(root), "--config", str(cfg), "--no-mcp-import"]
        assert agentsync.main(["apply", *common]) == 0

        for f in (root / ".claude/settings.json", root / ".copilot/settings.json"):
            s = json.loads(f.read_text())
            assert not any(m in json.dumps(s.get("hooks", {}))
                           for m in ("guard-commit", "session-nudge", "prompt-context")), \
                f"enforcement hook leaked into {f}"
        vh = json.loads((root / ".config/agentsync/vscode-hooks.json").read_text())
        assert vh == {"hooks": {}}, f"vscode determinism hooks not gated: {vh}"
        assert not (root / ".config/opencode/plugin/determinism.js").exists(), \
            "opencode plugin installed despite enforcement=false"
        # sync itself still works
        assert (root / ".claude/CLAUDE.md").is_symlink()
        assert (root / ".claude/mcp-servers.json").exists()
        assert agentsync.main(["verify", *common]) == 0, "verify dirty after apply"


if __name__ == "__main__":
    main()
