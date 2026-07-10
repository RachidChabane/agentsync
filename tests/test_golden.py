#!/usr/bin/env python3
"""Golden snapshot of the reconciler's observable output: apply a fixed fixture config
for all 8 harnesses (user scope) plus a project-scope repo, then compare every rendered
file and symlink target byte-for-byte against tests/golden/apply.json.

This is the refactor guard: any change to what config-sync writes — intended or not —
fails here until the golden is deliberately regenerated:

  GOLDEN_UPDATE=1 python3 tests/test_golden.py

Machine-dependent prefixes (sandbox root, config dir, repo checkout, the per-OS VS Code
user dir) are substituted with $-tokens so the committed golden is identical on macOS
and Linux CI. Run from repo root.
"""
import difflib
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import agentsync          # noqa: E402
from core.util import vscode_user_dir  # noqa: E402

GOLDEN = REPO / "tests" / "golden" / "apply.json"

FIXTURE_MCP = {"servers": {
    "context7": {"transport": "http", "url": "https://mcp.context7.com/mcp"},
    "db": {"transport": "stdio", "command": "npx", "args": ["-y", "db-mcp@latest"]},
    "secret": {"transport": "http", "url": "https://api.x.com/mcp",
               "auth": {"header": "x-key", "headersHelper": "~/.config/x/h.sh", "env": "X_KEY"},
               "opencode": {"enabled": False}},
}}
ALL = ["claude", "copilot", "opencode", "vscode", "cursor", "windsurf", "zed", "cline"]


def write_config(cfg: Path):
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "instructions.md").write_text("# Global\nbe deterministic\n")
    (cfg / "instructions.claude.md").write_text("## Claude-only\nuse rtk\n")
    (cfg / "mcp.json").write_text(json.dumps(FIXTURE_MCP))
    (cfg / "skills" / "local-skill").mkdir(parents=True)
    (cfg / "skills" / "local-skill" / "SKILL.md").write_text(
        "---\nname: local-skill\ndescription: fixture\n---\nbody\n")
    (cfg / "skills.json").write_text(json.dumps({"skills": {
        "local-skill": {"tier": "on", "source": str(cfg / "skills" / "local-skill")},
        "tier-only": "name-only", "hidden": "user-invocable-only", "dead": "off"}}))
    (cfg / "profile.json").write_text(json.dumps({"harnesses": ALL}))


def snapshot(top: Path, subs: list, skip=()) -> dict:
    """Absolute path -> content (or '-> target' for symlinks), with subs applied to
    both keys and values. Sorted, so the snapshot is order-stable."""
    def norm(s: str) -> str:
        for old, new in subs:
            s = s.replace(old, new)
        return s
    out = {}
    for p in sorted(top.rglob("*")):
        if any(part in skip for part in p.relative_to(top).parts):
            continue
        if p.is_symlink():
            out[norm(str(p))] = "-> " + norm(os.readlink(p))
        elif p.is_file():
            out[norm(str(p))] = norm(p.read_text())
    return out


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, proj = Path(tmp) / "home", Path(tmp) / "cfg", Path(tmp) / "proj"
        write_config(cfg)
        assert agentsync.main(["apply", "--root", str(root), "--config", str(cfg),
                               "--no-mcp-import"]) == 0, "user-scope apply failed"

        (proj / ".agentsync").mkdir(parents=True)
        (proj / ".agentsync" / "instructions.md").write_text("# Team rules\nno yolo\n")
        (proj / ".agentsync" / "mcp.json").write_text(json.dumps(FIXTURE_MCP))
        (proj / ".agentsync" / "profile.json").write_text(json.dumps({"harnesses": ALL}))
        assert agentsync.main(["apply", "--project", str(proj)]) == 0, "project apply failed"

        subs = [(str(vscode_user_dir(root)), "$VSCODE_USER"), (str(root), "$ROOT"),
                (str(proj), "$PROJ"), (str(cfg), "$CFG"), (str(REPO), "$REPO")]
        got = {"user": snapshot(root, subs),
               "project": snapshot(proj, subs, skip=(".agentsync",))}

    text = json.dumps(got, indent=1, sort_keys=True) + "\n"
    if os.environ.get("GOLDEN_UPDATE"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(text)
        print(f"test_golden: golden regenerated ({GOLDEN})")
        return
    assert GOLDEN.exists(), f"missing {GOLDEN} — run GOLDEN_UPDATE=1 python3 tests/test_golden.py"
    want = GOLDEN.read_text()
    if text != want:
        sys.stdout.writelines(difflib.unified_diff(
            want.splitlines(True), text.splitlines(True),
            fromfile="golden", tofile="rendered"))
        raise AssertionError("rendered output changed — if intended, regenerate the golden")
    print("test_golden: PASS")


if __name__ == "__main__":
    main()
