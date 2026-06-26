#!/usr/bin/env python3
"""Lifecycle checks (slice A): backup-on-merge, stale-hook cleanup + drift visibility,
`diff` writes nothing, and uninstall surgically removes only what we added. Sandbox root;
never touches $HOME. Run from repo root.
"""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import agentsync  # noqa: E402


def write_cfg(d: Path):
    d.mkdir(parents=True, exist_ok=True)
    (d / "instructions.md").write_text("# Global\nx\n")
    (d / "mcp.json").write_text('{"servers":{"context7":{"transport":"http","url":"https://mcp.context7.com/mcp"}}}')
    (d / "skills.json").write_text('{"skills":{"a":"on","b":"user-invocable-only"}}')
    (d / "profile.json").write_text('{"harnesses":["claude","copilot","opencode"]}')


def guards(settings: dict):
    return [h["command"] for g in settings.get("hooks", {}).get("PreToolUse", [])
            for h in g.get("hooks", []) if "guard-commit.sh" in h.get("command", "")]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root, conf = Path(tmp) / "home", Path(tmp) / "cfg"
        write_cfg(conf)
        common = ["--root", str(root), "--config", str(conf), "--no-mcp-import"]
        cs = root / ".claude" / "settings.json"

        # Seed unrelated user content the tool must preserve through everything.
        cs.parent.mkdir(parents=True)
        cs.write_text(json.dumps({"theme": "dark"}))

        assert agentsync.main(["apply", *common]) == 0
        assert agentsync.main(["verify", *common]) == 0, "verify dirty after apply"

        # A4: original backed up exactly once.
        bak = cs.with_name("settings.json.bak")
        assert bak.exists() and json.loads(bak.read_text()) == {"theme": "dark"}, "no/bad backup"

        # A3: a stale agentsync hook (old repo path) is drift, and apply cleans it to one.
        data = json.loads(cs.read_text())
        data["hooks"]["PreToolUse"].append(
            {"matcher": "Bash", "hooks": [{"type": "command", "command": '"/old/p/guard-commit.sh"'}]})
        cs.write_text(json.dumps(data))
        assert agentsync.main(["verify", *common]) == 1, "stale hook not seen as drift"
        assert agentsync.main(["apply", *common]) == 0
        g = guards(json.loads(cs.read_text()))
        assert len(g) == 1 and "/old/p/" not in g[0], f"stale hook not cleaned: {g}"
        assert agentsync.main(["verify", *common]) == 0

        # C12: diff previews a pending change but writes nothing.
        data = json.loads(cs.read_text())
        data["hooks"]["SessionStart"] = []
        cs.write_text(json.dumps(data))
        before = cs.read_text()
        assert agentsync.main(["diff", *common]) == 0
        assert cs.read_text() == before, "diff wrote to disk!"
        agentsync.main(["apply", *common])  # reconverge

        # A5: uninstall removes only ours; unrelated user key survives.
        assert (root / ".claude/mcp-servers.json").exists()
        assert (root / ".config/opencode/plugin/determinism.js").is_symlink()
        assert agentsync.main(["uninstall", *common]) == 0
        final = json.loads(cs.read_text())
        assert "skillOverrides" not in final, "owned key not removed on uninstall"
        assert not guards(final), "commit gate not removed on uninstall"
        assert final.get("theme") == "dark", "lost unrelated user key on uninstall"
        assert not (root / ".claude/mcp-servers.json").exists(), "artifact not removed"
        assert not (root / ".config/opencode/plugin/determinism.js").exists(), "plugin link not removed"
        oc = json.loads((root / ".config/opencode/opencode.json").read_text())
        assert "mcp" not in oc and "skill" not in oc.get("permission", {}), "opencode keys not removed"

    print("test_lifecycle: PASS")


if __name__ == "__main__":
    main()
