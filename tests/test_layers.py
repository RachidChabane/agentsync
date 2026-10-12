#!/usr/bin/env python3
"""Config layers: `@include <dir>` in instructions.md pulls in a directory shaped like
the config dir — its text spliced at the line, its mcp/skills/overrides merged.

- unit: merge rules (named entries unique; objects merge, lists concatenate, scalars
  agree) and layer discovery/refusals (variant source, the config dir itself, nested
  directive in a layer's text, a layer without text);
- integration: every surface carries the layer (instructions, settings keys and hooks,
  MCP in each dialect, skill links), user and project scope;
- removal: deleting the one directive line and re-applying into the same root leaves
  no trace of the layer anywhere — files, backups, symlink targets — while the base
  config survives; verify reports the pending removal first;
- conflicts abort every verb before any write, naming the layer file and key path.

Sandbox dirs only; never touches $HOME. Plain asserts. Run from repo root.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import agentsync                                          # noqa: E402
from core.instructions import IncludeError, expand, layers          # noqa: E402
from core.layers import LayerConflict, merge_deep, merge_named      # noqa: E402
from core.util import vscode_user_dir                               # noqa: E402

TOKEN = "zephyrteam"   # appears in every piece of the layer, nowhere in the base
DIRECTIVE = "@include layers/zephyr/"
BASE_TEXT = f"# Global\nbe deterministic\n\n{DIRECTIVE}\n"
BASE_OVERRIDES = {"claude": {"effortLevel": "high",
                             "enabledPlugins": {"base-plugin@market": True}}}


def write_cfg(cfg: Path, base_text: str = BASE_TEXT, layer_overrides=None):
    layer = cfg / "layers" / "zephyr"
    (layer / "skills" / f"{TOKEN}-skill").mkdir(parents=True, exist_ok=True)
    (cfg / "instructions.md").write_text(base_text)
    (cfg / "mcp.json").write_text(json.dumps({"servers": {
        "context7": {"transport": "http", "url": "https://mcp.context7.com/mcp"}}}))
    (cfg / "overrides.json").write_text(json.dumps(BASE_OVERRIDES))
    (cfg / "profile.json").write_text(json.dumps(
        {"harnesses": ["claude", "copilot", "opencode", "vscode", "zed"]}))
    (layer / "instructions.md").write_text(f"## Zephyr team\nask {TOKEN} for reviews\n")
    (layer / "mcp.json").write_text(json.dumps({"servers": {
        f"{TOKEN}-tracker": {"transport": "http", "url": f"https://{TOKEN}.example/mcp"}}}))
    (layer / "skills.json").write_text(json.dumps({"skills": {
        f"{TOKEN}-skill": {"tier": "on", "source": str(layer / "skills" / f"{TOKEN}-skill")}}}))
    (layer / "overrides.json").write_text(json.dumps(layer_overrides if layer_overrides is not None else {
        "claude": {"enabledPlugins": {f"{TOKEN}@market": True},
                   "hooks": {"UserPromptSubmit": [
                       {"hooks": [{"type": "command", "command": f"{TOKEN}-reminders"}]}]}},
        "vscode": {"chat.agentFilesLocations": {f"/srv/{TOKEN}/agents": True}},
    }))


def run(argv) -> tuple:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = agentsync.main(argv)
    return code, out.getvalue()


def expect(exc, fn, *fragments):
    try:
        fn()
    except exc as e:
        for f in fragments:
            assert f in str(e), f"{f!r} missing from: {e}"
        return
    raise AssertionError(f"expected {exc.__name__}")


def traces(root: Path) -> list:
    """Every file, backup, or symlink target under root that mentions the layer."""
    hits = []
    for p in root.rglob("*"):
        if p.is_symlink():
            if TOKEN in os.readlink(p):
                hits.append(f"{p} -> {os.readlink(p)}")
        elif p.is_file() and TOKEN in p.read_text(errors="replace"):
            hits.append(str(p))
    return hits


# --- unit -------------------------------------------------------------------------

def unit_merge_rules():
    src = Path("layers/x/overrides.json")
    assert merge_deep({"a": {"b": [1], "c": True}}, {"a": {"b": [1, 2], "d": 3}}, src) \
        == {"a": {"b": [1, 2], "c": True, "d": 3}}
    assert merge_deep({"a": "same"}, {"a": "same"}, src) == {"a": "same"}
    expect(LayerConflict, lambda: merge_deep({"claude": {"effortLevel": "high"}},
                                             {"claude": {"effortLevel": "low"}}, src),
           "layers/x/overrides.json", "claude.effortLevel")
    expect(LayerConflict, lambda: merge_named({"ctx": 1}, {"ctx": 2, "new": 3}, "servers",
                                              Path("layers/x/mcp.json")),
           "layers/x/mcp.json", "servers", "ctx")
    assert merge_named({"a": 1}, {"b": 2}, "skills", src) == {"a": 1, "b": 2}


def unit_layer_discovery_and_refusals():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp)
        write_cfg(cfg)
        (cfg / "instructions").mkdir()
        (cfg / "instructions" / "plain.md").write_text("plain\n")
        (cfg / "instructions.md").write_text(
            BASE_TEXT + "@include instructions/plain.md\n```\n@include layers/fenced/\n```\n")
        assert layers(cfg) == [(cfg / "layers" / "zephyr").resolve()], layers(cfg)
        assert f"ask {TOKEN} for reviews\n" in expand(cfg / "instructions.md", cfg)

        (cfg / "instructions.claude.md").write_text(f"{DIRECTIVE}\n")
        expect(IncludeError, lambda: expand(cfg / "instructions.claude.md", cfg),
               "instructions.claude.md:1", "only be included from the shared instructions.md")
        (cfg / "instructions.claude.md").unlink()

        (cfg / "instructions.md").write_text("@include ./\n")
        expect(IncludeError, lambda: expand(cfg / "instructions.md", cfg), "cyclic")

        (cfg / "layers" / "zephyr" / "instructions.md").write_text("@include ../../instructions/plain.md\n")
        (cfg / "instructions.md").write_text(BASE_TEXT)
        expect(IncludeError, lambda: expand(cfg / "instructions.md", cfg), "nested")

        (cfg / "layers" / "zephyr" / "instructions.md").unlink()
        assert expand(cfg / "instructions.md", cfg) == "# Global\nbe deterministic\n\n", \
            "a layer without instructions.md splices nothing"


# --- integration + removal ----------------------------------------------------------

def user_scope_layer_lifecycle():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg = Path(tmp) / "home", Path(tmp) / "cfg"
        write_cfg(cfg)
        common = ["--root", str(root), "--config", str(cfg), "--no-mcp-import"]
        assert run(["apply", *common])[0] == 0

        assert f"ask {TOKEN}" in (root / ".claude/CLAUDE.md").read_text()
        assert f"ask {TOKEN}" in (root / ".config/zed/AGENTS.md").read_text()
        cs = json.loads((root / ".claude/settings.json").read_text())
        assert cs["enabledPlugins"] == {"base-plugin@market": True, f"{TOKEN}@market": True}, \
            "layer plugins must merge with the base ones"
        assert cs["effortLevel"] == "high"
        assert any(f"{TOKEN}-reminders" in json.dumps(g) for g in cs["hooks"]["UserPromptSubmit"])
        assert f"{TOKEN}-tracker" in json.loads((root / ".claude/mcp-servers.json").read_text())
        assert f"{TOKEN}-tracker" in json.loads((root / ".copilot/mcp-config.json").read_text())["mcpServers"]
        assert f"{TOKEN}-tracker" in json.loads((root / ".config/opencode/opencode.json").read_text())["mcp"]
        vs = json.loads((vscode_user_dir(root) / "settings.json").read_text())
        assert f"/srv/{TOKEN}/agents" in vs["chat.agentFilesLocations"]
        assert (root / f".claude/skills/{TOKEN}-skill").is_symlink()
        assert (root / f".copilot/skills/{TOKEN}-skill").is_symlink()
        assert run(["verify", *common])[0] == 0

        # A hook another tool wrote into the same event must survive the removal.
        cs["hooks"]["UserPromptSubmit"].append(
            {"hooks": [{"type": "command", "command": "status-reporter"}]})
        (root / ".claude/settings.json").write_text(json.dumps(cs))

        (cfg / "instructions.md").write_text(BASE_TEXT.replace(DIRECTIVE + "\n", ""))
        code, out = run(["verify", *common])
        assert code == 1, "dropping the layer must read as drift until applied"
        assert run(["apply", *common])[0] == 0
        assert not traces(root), f"layer survived its directive: {traces(root)}"
        cs = json.loads((root / ".claude/settings.json").read_text())
        assert cs["enabledPlugins"] == {"base-plugin@market": True} and cs["effortLevel"] == "high", \
            "base config must survive the layer's removal"
        assert [h["command"] for g in cs["hooks"]["UserPromptSubmit"] for h in g["hooks"]] \
            == ["status-reporter"], "foreign hook lost, or layer hook kept"
        assert "context7" in json.loads((root / ".claude/mcp-servers.json").read_text())
        assert run(["verify", *common])[0] == 0


def project_scope_layer():
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "repo"
        write_cfg(proj / ".agentsync")
        (proj / ".agentsync" / "profile.json").write_text(json.dumps({"harnesses": ["claude", "copilot"]}))
        assert run(["apply", "--project", str(proj)])[0] == 0
        assert f"ask {TOKEN}" in (proj / "CLAUDE.md").read_text()
        assert f"{TOKEN}-tracker" in json.loads((proj / ".mcp.json").read_text())["mcpServers"]
        assert run(["verify", "--project", str(proj)])[0] == 0


def conflict_aborts_before_writes():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg = Path(tmp) / "home", Path(tmp) / "cfg"
        write_cfg(cfg, layer_overrides={"claude": {"effortLevel": "low"}})
        for verb in ("apply", "verify", "diff"):
            try:
                run([verb, "--root", str(root), "--config", str(cfg), "--no-mcp-import"])
            except SystemExit as e:
                msg = str(e.code)
                assert msg.startswith("error: ") and "overrides.json" in msg \
                    and "claude.effortLevel" in msg, msg
            else:
                raise AssertionError(f"{verb}: a layer conflict must abort")
        assert not root.exists(), "nothing may be written when layers conflict"


def main():
    unit_merge_rules()
    unit_layer_discovery_and_refusals()
    user_scope_layer_lifecycle()
    project_scope_layer()
    conflict_aborts_before_writes()
    print("test_layers: PASS")


if __name__ == "__main__":
    main()
