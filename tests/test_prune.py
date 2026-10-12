#!/usr/bin/env python3
"""Releasing what the config stops asking for. agentsync records what each adapter put
in place (.config/agentsync/managed.json); the next run releases exactly that and
nothing else:

- an owned settings key dropped from overrides.json leaves the settings file;
- a passthrough hook group dropped from overrides.json leaves, while a hook agentsync
  never wrote in the same event stays;
- turning enforcement off removes the gate and nudge hooks;
- a skill dropped from skills.json loses its links, but a user's own link is kept;
- verify reports each pending release as drift, and diff shows it;
- a path another running adapter still declares is kept; one nobody declares goes;
- uninstall releases stale entries too and leaves no record behind.

Sandbox dirs only; never touches $HOME. Plain asserts. Run from repo root.
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import agentsync               # noqa: E402
from core.util import vscode_user_dir    # noqa: E402

FOREIGN_HOOK = {"hooks": [{"type": "command", "command": "status-reporter --event prompt"}]}
REMINDER_HOOK = {"hooks": [{"type": "command", "command": "reminders --mode claude"}]}
OVERRIDES = {
    "claude": {"effortLevel": "high", "hooks": {"UserPromptSubmit": [REMINDER_HOOK]}},
    "vscode": {"chat.agentFilesLocations": {"/srv/team/agents": True}},
}


def write_cfg(cfg: Path, overrides=None, skills=None, profile=None):
    (cfg / "skills" / "team-skill").mkdir(parents=True, exist_ok=True)
    (cfg / "skills" / "kept-skill").mkdir(parents=True, exist_ok=True)
    (cfg / "instructions.md").write_text("# Global\nbe deterministic\n")
    (cfg / "mcp.json").write_text(json.dumps({"servers": {}}))
    (cfg / "overrides.json").write_text(json.dumps(OVERRIDES if overrides is None else overrides))
    (cfg / "skills.json").write_text(json.dumps({"skills": skills if skills is not None else {
        "team-skill": {"tier": "on", "source": str(cfg / "skills" / "team-skill")},
        "kept-skill": {"tier": "on", "source": str(cfg / "skills" / "kept-skill")},
    }}))
    (cfg / "profile.json").write_text(json.dumps(
        profile or {"harnesses": ["claude", "copilot", "opencode", "vscode"]}))


def run(argv) -> tuple:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = agentsync.main(argv)
    return code, out.getvalue()


def hook_commands(settings: dict, event: str) -> list:
    return [h["command"] for g in settings.get("hooks", {}).get(event, [])
            for h in g.get("hooks", [])]


def releases_what_the_config_drops():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg = Path(tmp) / "home", Path(tmp) / "cfg"
        write_cfg(cfg)
        common = ["--root", str(root), "--config", str(cfg), "--no-mcp-import"]
        assert run(["apply", *common])[0] == 0

        cs_path = root / ".claude/settings.json"
        cs = json.loads(cs_path.read_text())
        cs["hooks"]["UserPromptSubmit"].append(FOREIGN_HOOK)  # written by another tool
        cs["theme"] = "dark"
        cs_path.write_text(json.dumps(cs))
        own_link = root / ".copilot/skills/handmade"
        own_link.symlink_to(cfg / "skills" / "team-skill")    # the user's, not recorded
        assert run(["verify", *common])[0] == 0

        write_cfg(cfg, overrides={"claude": {}, "vscode": {}},
                  skills={"kept-skill": {"tier": "on", "source": str(cfg / "skills" / "kept-skill")}})
        code, out = run(["verify", *common])
        assert code == 1, "a pending release must read as drift"
        assert "no longer configured" in out, out
        code, out = run(["diff", *common])
        assert code == 0 and "-" in out and "reminders --mode claude" in out, out

        assert run(["apply", *common])[0] == 0
        cs = json.loads(cs_path.read_text())
        assert "effortLevel" not in cs, "dropped owned key survived"
        assert hook_commands(cs, "UserPromptSubmit") == ["status-reporter --event prompt"], \
            "dropped hook survived, or a foreign hook was removed"
        assert cs["theme"] == "dark", "unrelated user key lost"
        vs = json.loads((vscode_user_dir(root) / "settings.json").read_text())
        assert "chat.agentFilesLocations" not in vs, "dropped VS Code key survived"
        for base in (root / ".claude/skills", root / ".copilot/skills"):
            assert not (base / "team-skill").exists(), f"stale skill link survived in {base}"
            assert (base / "kept-skill").is_symlink()
        assert own_link.is_symlink(), "a link agentsync never recorded must be kept"
        assert run(["verify", *common])[0] == 0, "did not converge after release"

        # Uninstall: nothing recorded is left, foreign content stays, record is gone.
        assert run(["uninstall", *common])[0] == 0
        cs = json.loads(cs_path.read_text())
        assert hook_commands(cs, "UserPromptSubmit") == ["status-reporter --event prompt"]
        assert not (root / ".config/agentsync/managed.json").exists(), "record left behind"


def enforcement_off_releases_the_gate():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg = Path(tmp) / "home", Path(tmp) / "cfg"
        write_cfg(cfg, overrides={})
        common = ["--root", str(root), "--config", str(cfg), "--no-mcp-import"]
        assert run(["apply", *common])[0] == 0
        assert "guard-commit.sh" in (root / ".claude/settings.json").read_text()

        write_cfg(cfg, overrides={}, profile={"harnesses": ["claude", "copilot", "opencode", "vscode"],
                                              "enforcement": False})
        assert run(["apply", *common])[0] == 0
        for f in (root / ".claude/settings.json", root / ".copilot/settings.json"):
            text = f.read_text()
            assert "guard-commit.sh" not in text and "session-nudge.sh" not in text \
                and "prompt-context.sh" not in text, f"gate survived in {f}"
        assert not (root / ".config/opencode/plugin/determinism.js").exists(), \
            "OpenCode plugin link survived"
        assert run(["verify", *common])[0] == 0


def shared_path_kept_while_claimed():
    """Two adapters record the same project file; one stops declaring it. The other
    still renders it, so it stays — and once nobody declares it, it goes."""
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "repo"
        d = proj / ".agentsync"
        d.mkdir(parents=True)
        (d / "instructions.md").write_text("# Team rules\n")
        (d / "mcp.json").write_text(json.dumps({"servers": {}}))
        (d / "profile.json").write_text(json.dumps({"harnesses": ["claude", "zed", "cline"]}))
        assert run(["apply", "--project", str(proj)])[0] == 0
        record = d / "managed.json"
        data = json.loads(record.read_text())
        assert "AGENTS.md" in data["zed"] and "AGENTS.md" in data["cline"], data

        # Cline once recorded two files it no longer declares: one that claude still
        # renders, and one nobody declares any more.
        (proj / "LEGACY.md").write_text("old\n")
        data["cline"]["LEGACY.md"] = {"kind": "file"}
        data["cline"]["CLAUDE.md"] = {"kind": "file"}
        record.write_text(json.dumps(data))
        assert run(["apply", "--project", str(proj)])[0] == 0
        assert not (proj / "LEGACY.md").exists(), "a path nobody declares must be released"
        assert (proj / "CLAUDE.md").read_text() == "# Team rules\n", \
            "a path another running adapter declares must be kept"
        assert (proj / "AGENTS.md").read_text() == "# Team rules\n", "shared file lost"
        assert run(["verify", "--project", str(proj)])[0] == 0


def main():
    releases_what_the_config_drops()
    enforcement_off_releases_the_gate()
    shared_path_kept_while_claimed()
    print("test_prune: PASS")


if __name__ == "__main__":
    main()
