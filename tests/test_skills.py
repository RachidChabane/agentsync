#!/usr/bin/env python3
"""Slice B: skill sourcing (local dir + git clone) and settings passthrough (arbitrary
keys + additive user hooks), incl. uninstall cleanup. Sandbox root; hermetic git via a
local file:// repo (no network). Run from repo root.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import agentsync  # noqa: E402


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root, conf = tmp / "home", tmp / "cfg"

        # local-dir skill source
        local = tmp / "localskills" / "local1"
        local.mkdir(parents=True)
        (local / "SKILL.md").write_text("# local1\n")

        # git skill source (cloned via file://) with the skill under skills/gitskill
        repo = tmp / "skillrepo"
        (repo / "skills" / "gitskill").mkdir(parents=True)
        (repo / "skills" / "gitskill" / "SKILL.md").write_text("# gitskill\n")
        git(repo, "init", "-q"); git(repo, "add", "-A")
        git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x")

        conf.mkdir(parents=True)
        (conf / "instructions.md").write_text("# Global\nx\n")
        (conf / "mcp.json").write_text('{"servers":{}}')
        (conf / "profile.json").write_text('{"harnesses":["claude","copilot"]}')
        (conf / "skills.json").write_text(json.dumps({"skills": {
            "local1": {"tier": "name-only", "source": str(local)},
            "gitskill": {"tier": "on", "source": f"file://{repo}", "subpath": "skills/gitskill"},
            "plain": "on",
        }}))
        (conf / "overrides.json").write_text(json.dumps({
            "claude": {"effortLevel": "high",
                       "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "notify"}]}]}},
        }))
        common = ["--root", str(root), "--config", str(conf), "--no-mcp-import"]

        assert agentsync.main(["apply", *common]) == 0
        assert agentsync.main(["verify", *common]) == 0, "verify dirty after apply"

        # B9: skills symlinked into both harnesses; git one resolved from cache.
        for harness in (".claude", ".copilot"):
            assert (root / harness / "skills/local1").is_symlink()
            assert (root / harness / "skills/gitskill/SKILL.md").read_text() == "# gitskill\n"
        assert (root / harness / "skills/plain").exists() is False, "tier-only skill must not be linked"

        # B10: passthrough key + user hook present, determinism hooks NOT clobbered.
        cs = json.loads((root / ".claude/settings.json").read_text())
        assert cs["effortLevel"] == "high"
        assert {"type": "command", "command": "notify"} in cs["hooks"]["Stop"][0]["hooks"]
        det = [h["command"] for g in cs["hooks"]["PreToolUse"] for h in g["hooks"]]
        assert any("guard-commit.sh" in c for c in det), "passthrough clobbered determinism hook"
        assert "Stop" in cs["hooks"] and "SessionStart" in cs["hooks"]

        # uninstall removes ours (skill links, passthrough key, user hook + determinism).
        assert agentsync.main(["uninstall", *common]) == 0
        assert not (root / ".claude/skills/local1").exists(), "skill link not removed"
        cs = json.loads((root / ".claude/settings.json").read_text())
        assert "effortLevel" not in cs and "Stop" not in cs.get("hooks", {}), "passthrough not removed"

    print("test_skills: PASS")


if __name__ == "__main__":
    main()
