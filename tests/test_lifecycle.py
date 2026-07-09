#!/usr/bin/env python3
"""Lifecycle checks (slice A): backup-on-merge, stale-hook cleanup + drift visibility,
`diff` writes nothing, `--json` output for CI, and uninstall surgically removes only what
we added. Sandbox root; never touches $HOME. Run from repo root.
"""
import contextlib
import io
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


def run_json(argv):
    """Run the CLI capturing stdout; returns (exit_code, parsed JSON)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = agentsync.main(argv)
    return rc, json.loads(buf.getvalue())


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

        # J: --json is valid JSON, mirrors drift + exit code, and carries diff blocks.
        rc, out = run_json(["verify", "--json", *common])
        assert rc == 0 and out["drift"] is False, out
        assert {h["name"] for h in out["harnesses"]} == {"claude", "copilot", "opencode"}
        data = json.loads(cs.read_text())
        data["hooks"]["SessionStart"] = []
        cs.write_text(json.dumps(data))
        rc, out = run_json(["verify", "--json", *common])
        assert rc == 1 and out["drift"] is True, "json verify missed drift"
        claude = next(h for h in out["harnesses"] if h["name"] == "claude")
        assert claude["drift"] and any(l["status"] == "drift" for l in claude["lines"])
        rc, out = run_json(["diff", "--json", *common])
        assert rc == 0, "diff --json must keep diff's exit code"
        assert any(h["diffs"] for h in out["harnesses"]), "diff --json lost the diff blocks"
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

    resolve_config_checks()
    print("test_lifecycle: PASS")


def resolve_config_checks():
    """Config-dir resolution: --config wins; repo config/ then config.example/; an
    installed CLI (no repo dirs) falls back to ~/.config/agentsync or errors clearly."""
    from unittest import mock
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        repo, home = tmp / "repo", tmp / "home"
        (home / ".config/agentsync").mkdir(parents=True)
        assert agentsync.resolve_config(str(tmp / "explicit"), repo) == tmp / "explicit"
        with mock.patch.object(Path, "home", return_value=home):
            assert agentsync.resolve_config(None, repo) == home / ".config/agentsync"
            (repo / "config.example").mkdir(parents=True)
            assert agentsync.resolve_config(None, repo) == repo / "config.example"
            (repo / "config").mkdir()
            assert agentsync.resolve_config(None, repo) == repo / "config"
            with mock.patch.object(Path, "home", return_value=tmp / "nohome"):
                try:
                    agentsync.resolve_config(None, tmp / "norepo")
                    raise AssertionError("expected a clear error with no config anywhere")
                except SystemExit as e:
                    assert "no config found" in str(e)


if __name__ == "__main__":
    main()
