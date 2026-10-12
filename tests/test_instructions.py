#!/usr/bin/env python3
"""`@include` composition of the instructions, at three levels:

- unit: the expansion rules of core/instructions.py (splicing, fenced/indented/inline
  text left alone, missing / outside / nested / cyclic targets refused with file:line);
- integration: every adapter, user and project scope, renders the included text and
  never the raw directive — including OpenCode, which reads instruction files by path;
- reconcile: verify reports drift and diff shows the hunk when only an included file
  changes; a pre-existing symlink becomes an owned file without writing through to the
  source; dropping the directive drops the text; a bad directive fails before writes.

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
from core import agentsync                                    # noqa: E402
from core.adapters import ADAPTERS                            # noqa: E402
from core.instructions import IncludeError, directives, expand  # noqa: E402
from core.util import vscode_user_dir                         # noqa: E402

BASE = "# Global\nbe deterministic\n\n@include instructions/team.md\n\n## Tail\nlast rule\n"
TEAM = "## Team rules\nuse the shared runner\n"
DIRECTIVE = "@include instructions/team.md"
MCP = {"servers": {"context7": {"transport": "http", "url": "https://mcp.context7.com/mcp"}}}


def write_cfg(cfg: Path, base: str = BASE, team: str = TEAM, harnesses=None):
    (cfg / "instructions").mkdir(parents=True, exist_ok=True)
    (cfg / "instructions.md").write_text(base)
    (cfg / "instructions" / "team.md").write_text(team)
    (cfg / "mcp.json").write_text(json.dumps(MCP))
    (cfg / "profile.json").write_text(json.dumps({"harnesses": harnesses or list(ADAPTERS)}))


def expect_error(fn, *fragments):
    try:
        fn()
    except IncludeError as e:
        for f in fragments:
            assert f in str(e), f"{f!r} missing from error: {e}"
        return str(e)
    raise AssertionError("expected IncludeError")


def run(argv) -> tuple:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = agentsync.main(argv)
    return code, out.getvalue()


# --- unit -------------------------------------------------------------------------

def unit_splice():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp)
        write_cfg(cfg)
        out = expand(cfg / "instructions.md", cfg)
        assert out == "# Global\nbe deterministic\n\n" + TEAM + "\n## Tail\nlast rule\n", out
        assert "@include" not in out

        (cfg / "plain.md").write_text("# no directives\n")
        assert expand(cfg / "plain.md", cfg) == "# no directives\n", "identity without directives"

        (cfg / "instructions" / "team.md").write_text("no trailing newline")
        assert "no trailing newline\n\n## Tail" in expand(cfg / "instructions.md", cfg), \
            "an included file without a final newline must not glue onto the next line"

        (cfg / "instructions" / "team.md").write_text("")
        assert expand(cfg / "instructions.md", cfg) == "# Global\nbe deterministic\n\n\n## Tail\nlast rule\n"


def unit_not_directives():
    text = ("```md\n@include fenced.md\n```\n"
            "~~~~\n@include tilde.md\n```\n@include still-fenced.md\n~~~~\n"
            "    @include indented.md\n"
            "write @include x.md mid-sentence\n"
            "@includes plural.md\n"
            "@include\n"
            "@include real.md   \n")
    found = directives(text)
    assert [(d.target, d.line_no) for d in found] == [("real.md", 13)], found


def unit_refusals():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "cfg"
        (cfg / "instructions").mkdir(parents=True)
        src = cfg / "instructions.md"

        src.write_text("# x\n@include instructions/absent.md\n")
        expect_error(lambda: expand(src, cfg), f"{src}:2", "not found", "absent.md")

        (Path(tmp) / "outside.md").write_text("secret\n")
        src.write_text("@include ../outside.md\n")
        expect_error(lambda: expand(src, cfg), f"{src}:1", "outside the config directory")

        src.write_text("# x\n\n@include instructions.md\n")
        expect_error(lambda: expand(src, cfg), f"{src}:3", "cyclic", "includes itself")

        (cfg / "instructions" / "a.md").write_text("# a\n@include ../instructions.md\n")
        src.write_text("@include instructions/a.md\n")
        expect_error(lambda: expand(src, cfg), f"{cfg / 'instructions' / 'a.md'}:2", "cyclic")

        (cfg / "instructions" / "b.md").write_text("# b\n")
        (cfg / "instructions" / "a.md").write_text("# a\n\n@include b.md\n")
        expect_error(lambda: expand(src, cfg), f"{cfg / 'instructions' / 'a.md'}:3",
                     "nested @include is not supported", "b.md")

        (cfg / "instructions" / "a.md").write_text("```\n@include b.md\n```\n")
        assert "@include b.md" in expand(src, cfg), "a fenced directive in an included file is text"


# --- integration: every adapter, both scopes ----------------------------------------

def user_scope_every_adapter():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg = Path(tmp) / "home", Path(tmp) / "cfg"
        write_cfg(cfg)
        (cfg / "instructions.claude.md").write_text("## Claude-only\nuse the CLI\n")
        common = ["--root", str(root), "--config", str(cfg), "--no-mcp-import"]
        assert run(["apply", *common])[0] == 0

        expanded = expand(cfg / "instructions.md", cfg)
        files = {
            "claude": root / ".claude/CLAUDE.md",
            "copilot": root / ".copilot/copilot-instructions.md",
            "windsurf": root / ".codeium/windsurf/memories/global_rules.md",
            "zed": root / ".config/zed/AGENTS.md",
            "cline": root / "Documents/Cline/Rules/agentsync.md",
        }
        for name, f in files.items():
            assert not f.is_symlink(), f"{name}: a symlink would expose the raw directive"
            text = f.read_text()
            assert TEAM in text and DIRECTIVE not in text, f"{name}: {text!r}"
        assert files["copilot"].read_text() == expanded
        assert files["claude"].read_text().endswith("## Claude-only\nuse the CLI\n"), \
            "variant still appended after the expanded shared text"

        oc = json.loads((root / ".config/opencode/opencode.json").read_text())
        rendered = root / ".config/agentsync/opencode-instructions.md"
        assert oc["instructions"] == [str(rendered)], oc["instructions"]
        assert rendered.read_text() == expanded

        vs = json.loads((vscode_user_dir(root) / "settings.json").read_text())
        assert vs["github.copilot.chat.codeGeneration.instructions"][0]["text"] == expanded

        assert run(["verify", *common])[0] == 0, "verify dirty right after apply"
        assert (cfg / "instructions.md").read_text() == BASE, "source must never be rewritten"


def project_scope_every_adapter():
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "repo"
        write_cfg(proj / ".agentsync")
        assert run(["apply", "--project", str(proj)])[0] == 0

        for rel in ("CLAUDE.md", ".github/copilot-instructions.md", "AGENTS.md",
                    ".opencode/agentsync-instructions.md"):
            text = (proj / rel).read_text()
            assert TEAM in text and DIRECTIVE not in text, f"{rel}: {text!r}"
        oc = json.loads((proj / "opencode.json").read_text())
        assert oc["instructions"] == [".opencode/agentsync-instructions.md"], \
            "project refs stay repo-relative"
        assert run(["verify", "--project", str(proj)])[0] == 0


# --- reconcile: drift, transition, removal, failure ----------------------------------

def drift_on_included_file():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg = Path(tmp) / "home", Path(tmp) / "cfg"
        write_cfg(cfg)
        common = ["--root", str(root), "--config", str(cfg), "--no-mcp-import"]
        assert run(["apply", *common])[0] == 0

        (cfg / "instructions" / "team.md").write_text(TEAM + "pin every dependency\n")
        code, out = run(["verify", *common])
        assert code == 1, "an edit to an included file alone must read as drift"
        assert "CLAUDE.md would change" in out, out

        code, out = run(["diff", *common])
        assert code == 0 and "+pin every dependency" in out, out

        code, out = run(["verify", "--json", *common])
        report = json.loads(out)
        assert code == 1 and report["drift"] is True
        drifted = {h["name"] for h in report["harnesses"] if h["drift"]}
        assert drifted == set(ADAPTERS) - {"cursor"}, drifted  # cursor has no instructions

        assert run(["apply", *common])[0] == 0
        assert run(["verify", *common])[0] == 0, "did not re-converge"
        assert "pin every dependency" in (root / ".claude/CLAUDE.md").read_text()


def files_under(root: Path) -> list:
    return [f for f in root.rglob("*") if f.is_file() and not f.is_symlink()]


def upgrade_from_symlink_then_remove_include():
    """The real sequence: an older install left symlinks; apply with the directive;
    drop the directive and apply again into the SAME root. Nothing of the included text
    may survive anywhere under root — not in a rendered file, a `.bak`, or an orphan."""
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg = Path(tmp) / "home", Path(tmp) / "cfg"
        write_cfg(cfg)
        common = ["--root", str(root), "--config", str(cfg), "--no-mcp-import"]
        old_style = [root / ".claude/CLAUDE.md", root / ".copilot/copilot-instructions.md"]
        for link in old_style:
            link.parent.mkdir(parents=True)
            link.symlink_to(cfg / "instructions.md")

        assert run(["apply", *common])[0] == 0
        for f in old_style:
            assert not f.is_symlink() and TEAM in f.read_text(), f
            assert not f.with_name(f.name + ".bak").exists(), "a symlink is not an original"
        assert (cfg / "instructions.md").read_text() == BASE, "wrote through the old symlink"

        (cfg / "instructions.md").write_text(BASE.replace(DIRECTIVE + "\n", ""))
        assert run(["apply", *common])[0] == 0
        leaks = [f for f in files_under(root) if "use the shared runner" in f.read_text()]
        assert not leaks, f"included text survived its directive: {leaks}"
        assert not list(root.rglob("*.bak")), "a rendered copy was kept as an original"
        assert run(["verify", *common])[0] == 0


def uninstall_restores_the_original():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg = Path(tmp) / "home", Path(tmp) / "cfg"
        write_cfg(cfg)
        common = ["--root", str(root), "--config", str(cfg), "--no-mcp-import"]
        claude_md = root / ".claude/CLAUDE.md"
        claude_md.parent.mkdir(parents=True)
        claude_md.write_text("# my own rules\n")

        assert run(["apply", *common])[0] == 0
        assert TEAM in claude_md.read_text()
        assert run(["uninstall", *common])[0] == 0
        assert claude_md.read_text() == "# my own rules\n", "original not restored"
        assert not (root / ".config/agentsync/opencode-instructions.md").exists(), \
            "rendered OpenCode file not removed"
        assert not (root / ".config/agentsync/originals.json").exists(), \
            "a full uninstall leaves no capture ledger behind"


def bad_directive_fails_before_any_write():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg = Path(tmp) / "home", Path(tmp) / "cfg"
        write_cfg(cfg)
        (cfg / "instructions.copilot.md").write_text("## extra\n@include instructions/gone.md\n")
        for verb in ("apply", "verify", "diff"):
            try:
                run([verb, "--root", str(root), "--config", str(cfg), "--no-mcp-import"])
            except SystemExit as e:
                msg = str(e.code)
                assert msg.startswith("error: ") and "instructions.copilot.md:2" in msg \
                    and "not found" in msg, msg
            else:
                raise AssertionError(f"{verb}: a missing include must abort")
        assert not root.exists(), "nothing may be written when a directive cannot expand"


def main():
    unit_splice()
    unit_not_directives()
    unit_refusals()
    user_scope_every_adapter()
    project_scope_every_adapter()
    drift_on_included_file()
    upgrade_from_symlink_then_remove_include()
    uninstall_restores_the_original()
    bad_directive_fails_before_any_write()
    print("test_instructions: PASS")


if __name__ == "__main__":
    main()
