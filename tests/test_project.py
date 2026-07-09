#!/usr/bin/env python3
"""New-harness rendering (cursor/windsurf/zed/cline) and project scope (--project):
committed team-shared files, per-tool MCP dialects, merge preservation, drift, and
uninstall. Sandbox dirs; never touches $HOME. Run from repo root.
"""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import agentsync  # noqa: E402

MCP = {"servers": {
    "context7": {"transport": "http", "url": "https://mcp.context7.com/mcp"},
    "db": {"transport": "stdio", "command": "npx", "args": ["-y", "db-mcp"]},
    "secret": {"transport": "http", "url": "https://api.x.com/mcp",
               "auth": {"header": "x-key", "env": "X_KEY"}},
}}


def write_cfg(d: Path, harnesses):
    d.mkdir(parents=True, exist_ok=True)
    (d / "instructions.md").write_text("# Team rules\nbe deterministic\n")
    (d / "mcp.json").write_text(json.dumps(MCP))
    (d / "profile.json").write_text(json.dumps({"harnesses": harnesses}))


def user_scope_new_harnesses():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg = Path(tmp) / "home", Path(tmp) / "cfg"
        write_cfg(cfg, ["cursor", "windsurf", "zed", "cline"])
        common = ["--root", str(root), "--config", str(cfg), "--no-mcp-import"]

        # Pre-seed cursor's shared MCP file: user's own server must survive the merge.
        (root / ".cursor").mkdir(parents=True)
        (root / ".cursor/mcp.json").write_text(json.dumps(
            {"mcpServers": {"mine": {"command": "x"}}, "unrelated": True}))

        assert agentsync.main(["apply", *common]) == 0

        cur = json.loads((root / ".cursor/mcp.json").read_text())
        assert cur["unrelated"] is True, "clobbered user's top-level key"
        assert "mine" not in cur["mcpServers"], "mcpServers key is owned wholesale"
        assert cur["mcpServers"]["context7"] == {"url": "https://mcp.context7.com/mcp"}, \
            "cursor remote entries must have no type field"
        assert cur["mcpServers"]["secret"]["headers"] == {"x-key": "${X_KEY}"}

        ws = json.loads((root / ".codeium/windsurf/mcp_config.json").read_text())
        assert ws["mcpServers"]["context7"] == {"serverUrl": "https://mcp.context7.com/mcp"}, \
            "windsurf remote entries use serverUrl"
        assert (root / ".codeium/windsurf/memories/global_rules.md").is_symlink()

        assert (root / ".config/zed/AGENTS.md").is_symlink()
        assert not (root / ".config/zed/settings.json").exists(), "zed manages no MCP (JSONC)"

        cl = json.loads((root / ".cline/mcp.json").read_text())
        assert cl["mcpServers"]["context7"]["type"] == "streamableHttp"
        assert cl["mcpServers"]["db"] == {"command": "npx", "args": ["-y", "db-mcp"]}
        assert (root / "Documents/Cline/Rules/agentsync.md").is_symlink()

        assert agentsync.main(["verify", *common]) == 0, "verify dirty after apply"
        assert agentsync.main(["uninstall", *common]) == 0
        cur = json.loads((root / ".cursor/mcp.json").read_text())
        assert "mcpServers" not in cur and cur["unrelated"] is True, "uninstall not surgical"


def project_scope():
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "repo"
        write_cfg(proj / ".agentsync",
                  ["claude", "copilot", "opencode", "vscode", "cursor", "zed"])
        (proj / ".agentsync" / "instructions.claude.md").write_text("## Claude extra\n")
        common = ["--project", str(proj)]

        # Pre-seed a shared project file with unrelated keys to preserve.
        (proj / ".vscode").mkdir(parents=True)
        (proj / ".vscode/mcp.json").write_text(json.dumps({"inputs": [{"id": "tok"}]}))

        assert agentsync.main(["apply", *common]) == 0

        cm = (proj / "CLAUDE.md").read_text()
        assert cm.startswith("# Team rules") and "## Claude extra" in cm, "variant not applied"
        mcp = json.loads((proj / ".mcp.json").read_text())
        assert mcp["mcpServers"]["context7"] == {"type": "http", "url": "https://mcp.context7.com/mcp"}
        assert mcp["mcpServers"]["secret"]["headers"] == {"x-key": "${X_KEY}"}, \
            "teammates need env headers, not headersHelper"
        assert (proj / ".github/copilot-instructions.md").read_text().startswith("# Team rules")
        assert (proj / "AGENTS.md").read_text().startswith("# Team rules")

        oc = json.loads((proj / "opencode.json").read_text())
        assert oc["instructions"] == [".agentsync/instructions.md"], "must be repo-relative"
        vs = json.loads((proj / ".vscode/mcp.json").read_text())
        assert vs["inputs"] == [{"id": "tok"}], "clobbered user's inputs key"
        assert vs["servers"]["secret"]["headers"] == {"x-key": "${env:X_KEY}"}
        cur = json.loads((proj / ".cursor/mcp.json").read_text())
        assert "url" in cur["mcpServers"]["context7"]

        # No user-scope leakage: nothing outside the project dir, no skills/docs dirs.
        assert not (proj / ".agentsync/docs").exists(), "inventory docs are user-scope"

        # Idempotent + drift + uninstall.
        assert agentsync.main(["verify", *common]) == 0, "verify dirty after apply"
        (proj / ".mcp.json").write_text(json.dumps({"mcpServers": {}}))
        assert agentsync.main(["verify", *common]) == 1, "drift not detected"
        assert agentsync.main(["apply", *common]) == 0
        assert agentsync.main(["uninstall", *common]) == 0
        assert not (proj / "CLAUDE.md").exists(), "owned file not removed"
        vs = json.loads((proj / ".vscode/mcp.json").read_text())
        assert "servers" not in vs and vs["inputs"] == [{"id": "tok"}], "uninstall not surgical"

        # A user-scope-heavy harness still only writes committed files at project scope.
        (proj / ".agentsync/profile.json").write_text(json.dumps({"harnesses": ["windsurf"]}))
        assert agentsync.main(["apply", *common]) == 0
        assert (proj / "AGENTS.md").exists() and not (proj / ".codeium").exists()


def main():
    user_scope_new_harnesses()
    project_scope()
    print("test_project: PASS")


if __name__ == "__main__":
    main()
