#!/usr/bin/env python3
"""plugpack: canonical bundle -> Claude + Copilot plugin trees. Covers: skill byte-
identity, mechanical vs lossy agent remap (tool map, name synthesis, escapes, MCP
globs incl. Claude's plugin-qualified names), the warn-never-silent policy, dual
manifests/marketplaces, prune-on-repack, --check drift and --strict. Uses the
committed examples/demo-bundle as the fixture. Run from repo root."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import plugpack  # noqa: E402

BUNDLE = REPO / "examples" / "demo-bundle"


def rendering(out: Path):
    assert plugpack.main([str(BUNDLE), "--out", str(out)]) == 0

    # skills: byte-for-byte pass-through in BOTH trees
    src = (BUNDLE / "skills/greet/SKILL.md").read_bytes()
    for t in ("claude", "copilot"):
        assert (out / t / "plugins/demo/skills/greet/SKILL.md").read_bytes() == src

    # mechanical remap: named agent, mapped tools, model kept for claude only
    cr = (out / "claude/plugins/demo/agents/reviewer.md").read_text()
    assert "tools: Read, Grep, Glob, LSP" in cr, cr          # comma STRING + escape
    assert "model: haiku" in cr and "name: reviewer" in cr
    co = (out / "copilot/plugins/demo/agents/reviewer.agent.md").read_text()
    assert "tools: ['read', 'search']" in co, co             # YAML array, no escape
    assert "model" not in co and "LSP" not in co

    # lossy remap: name synthesized from filename; bundled server gets Claude's
    # plugin-qualified MCP name; handoffs/argument-hint are copilot-only
    cl = (out / "claude/plugins/demo/agents/librarian.md").read_text()
    assert "name: librarian" in cl
    assert "mcp__plugin_demo_docs" in cl
    assert "handoffs" not in cl and "argument-hint" not in cl
    assert "githubRepo" not in cl, "unmappable tool leaked instead of dropping"
    col = (out / "copilot/plugins/demo/agents/librarian.agent.md").read_text()
    assert "'docs/*'" in col and "'read/problems'" in col
    assert "handoffs:\n  - label: Implement it" in col
    assert "githubRepo" not in col

    # commands: Claude surface only, verbatim
    assert (out / "claude/plugins/demo/commands/hello.md").read_bytes() \
        == (BUNDLE / "commands/hello.md").read_bytes()
    assert not (out / "copilot/plugins/demo/commands").exists()

    # MCP dialects: bare keys for claude, mcpServers wrapper for copilot
    cm = json.loads((out / "claude/plugins/demo/.mcp.json").read_text())
    assert cm == json.loads((BUNDLE / "mcp.json").read_text())
    assert "mcpServers" not in cm
    assert json.loads((out / "copilot/plugins/demo/.mcp.json").read_text()) \
        == {"mcpServers": cm}

    # manifests + marketplaces
    cp = json.loads((out / "claude/plugins/demo/.claude-plugin/plugin.json").read_text())
    assert cp["name"] == "demo" and "skills" not in cp, "claude auto-discovers"
    cop = json.loads((out / "copilot/plugins/demo/.github/plugin/plugin.json").read_text())
    assert cop["skills"] == ["./skills/greet/"] and cop["mcpServers"] == ".mcp.json"
    assert "agents" not in cop, "explicit agents conflicts across copilot validators"
    cmk = json.loads((out / "claude/.claude-plugin/marketplace.json").read_text())
    assert cmk["owner"] == {"name": "agentsync"}
    assert cmk["plugins"][0]["source"] == "./plugins/demo"
    comk = json.loads((out / "copilot/.github/plugin/marketplace.json").read_text())
    assert comk["metadata"]["version"] == "0.1.0"
    assert comk["plugins"][0]["source"] == "plugins/demo"


def warnings():
    _, warns = plugpack.render(BUNDLE)
    text = "\n".join(warns)
    for expected in ("unknown tool 'githubRepo'", "model 'haiku'",
                     "'handoffs' has no Claude surface",
                     "'argument-hint' has no Claude surface",
                     "command hello: not rendered for copilot"):
        assert expected in text, f"missing warning: {expected}\n{text}"
    assert len(warns) == 5, warns
    # --strict turns those warnings into exit 2
    with tempfile.TemporaryDirectory() as tmp:
        assert plugpack.main([str(BUNDLE), "--out", tmp, "--strict"]) == 2


def drift_and_prune(out: Path):
    common = [str(BUNDLE), "--out", str(out)]
    assert plugpack.main(common) == 0, "repack must be idempotent"
    assert plugpack.main([*common, "--check"]) == 0, "clean check right after pack"

    edited = out / "claude/plugins/demo/agents/reviewer.md"
    edited.write_text(edited.read_text() + "\nrogue edit\n")
    (out / "copilot/plugins/demo/stray.txt").write_text("not ours? it is now\n")
    assert plugpack.main([*common, "--check"]) == 1, "hand-edit + stray must be drift"
    assert plugpack.main(common) == 0                 # converge: rewrite + prune
    assert "rogue edit" not in edited.read_text()
    assert not (out / "copilot/plugins/demo/stray.txt").exists()
    assert plugpack.main([*common, "--check"]) == 0

    # --tool limits both rendering and ownership
    assert plugpack.main([str(BUNDLE), "--out", str(out), "--tool", "claude", "--check"]) == 0


def removed_agent_pruned():
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "bundle", Path(tmp) / "dist"
        shutil.copytree(BUNDLE, src)
        assert plugpack.main([str(src), "--out", str(out)]) == 0
        (src / "agents/librarian.md").unlink()
        assert plugpack.main([str(src), "--out", str(out)]) == 0
        assert not (out / "claude/plugins/demo/agents/librarian.md").exists()
        assert not (out / "copilot/plugins/demo/agents/librarian.agent.md").exists()


def author_errors():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "bundle"
        shutil.copytree(BUNDLE, src)
        # two agents colliding on the kebab-cased Claude name
        (src / "agents/My Reviewer.md").write_text(
            "---\nname: My. Reviewer\ndescription: dup\n---\nbody\n")
        (src / "agents/aaa.md").write_text(
            "---\nname: my-reviewer\ndescription: dup\n---\nbody\n")
        try:
            plugpack.render(src)
            raise AssertionError("claude-name collision not rejected")
        except SystemExit as e:
            assert "my-reviewer" in str(e)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "bundle"
        shutil.copytree(BUNDLE, src)
        (src / "mcp.json").write_text('{"mcpServers": {"x": {}}}')
        try:
            plugpack.render(src)
            raise AssertionError("wrapped mcp.json not rejected")
        except SystemExit as e:
            assert "bare server-name keys" in str(e)


def front_parser():
    fields, body = plugpack.parse_front(
        "---\nname: 'A: b'\ntools: [x, 'y/z']\nflag: true\nhandoffs:\n"
        "  - label: L\n    send: false\n  - label: M\n---\nbody line\n")
    assert fields["name"] == "A: b" and fields["tools"] == ["x", "y/z"]
    assert fields["flag"] is True
    assert fields["handoffs"] == [{"label": "L", "send": False}, {"label": "M"}]
    assert body == "body line\n"
    fields, body = plugpack.parse_front("no frontmatter\n")
    assert fields == {} and body == "no frontmatter\n"


def main():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "dist"
        rendering(out)
        drift_and_prune(out)
    warnings()
    removed_agent_pruned()
    author_errors()
    front_parser()
    print("test_plugpack: PASS")


if __name__ == "__main__":
    main()
