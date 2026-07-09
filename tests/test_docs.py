#!/usr/bin/env python3
"""Slice: auto-generated inventory docs. Checks the four files are produced, that a
folded YAML `description:` is parsed to one line, and that generation is idempotent
(so the `verify` drift-check is stable). Sandbox; run from repo root.
"""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import agentsync  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root, cfg = tmp / "home", tmp / "cfg"
        skill = cfg / "skills" / "myskill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: myskill\ndescription: >\n  First part of it.\n  Second part.\n---\nbody\n")
        (cfg / "instructions.md").write_text("# x\n")
        (cfg / "mcp.json").write_text('{"servers":{"context7":{"transport":"http","url":"https://mcp.context7.com/mcp"}}}')
        (cfg / "skills.json").write_text(json.dumps({"skills": {"myskill": {"tier": "name-only", "source": str(skill)}}}))
        (cfg / "profile.json").write_text('{"harnesses":["claude"]}')
        # top-level "_comment" (as config.example ships) must not crash the agents scan
        (cfg / "overrides.json").write_text('{"_comment": "note", "claude": {}}')
        common = ["--root", str(root), "--config", str(cfg)]

        assert agentsync.main(["docs", *common]) == 0
        docs = cfg / "docs"
        for g in ("skills", "mcps", "hooks", "agents"):
            assert (docs / f"{g}.md").exists(), f"missing {g}.md"

        skills_md = (docs / "skills.md").read_text()
        # folded description collapsed to one line:
        assert "**myskill** (`name-only`) — First part of it. Second part." in skills_md, skills_md
        assert "context7" in (docs / "mcps.md").read_text()
        assert "guard-commit" in (docs / "hooks.md").read_text() or "commit gate" in (docs / "hooks.md").read_text()

        # idempotent: second run leaves files byte-identical
        before = (docs / "skills.md").read_text()
        assert agentsync.main(["docs", *common]) == 0
        assert (docs / "skills.md").read_text() == before, "docs generation not idempotent"

    print("test_docs: PASS")


if __name__ == "__main__":
    main()
