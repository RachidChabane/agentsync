#!/usr/bin/env python3
"""Services: a config or layer declares install/uninstall commands for a background job.

- unit: declaration parsing (relative commands resolve against the declaring dir,
  absolute and bare ones stay), duplicate names and malformed specs are refused;
- lifecycle (real scripts, HOME pointed at a sandbox): install runs once, a re-apply and
  a verify leave it alone, changed commands reinstall, dropping the declaration (or the
  layer's @include line) runs the recorded uninstall and leaves no trace, a failing
  command keeps the record and is retried, `uninstall` releases everything;
- verify and diff report the difference as drift and execute nothing;
- a root other than the real home and project scope never execute or record anything.

Plain asserts. Never touches the real $HOME. Run from repo root.
"""
import contextlib
import io
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import agentsync                                        # noqa: E402
from core.layers import LayerConflict                              # noqa: E402
from core.services import declared, refuse_in_project              # noqa: E402
from core.util import ConfigError                                  # noqa: E402

TOKEN = "nimbusjob"      # appears in the layer's paths and nowhere in the base
DIRECTIVE = "@include layers/nimbus/"
SCRIPT = """#!/usr/bin/env bash
here="$(cd "$(dirname "$0")/.." && pwd -P)"
echo "$1 $2" >> "$here/calls.log"
if [ "$1" = uninstall ] && [ -e "$here/refuse-uninstall" ]; then echo "agent busy" >&2; exit 1; fi
"""


def spec(version: str) -> dict:
    return {"install": [f"script/{TOKEN}", "install", version],
            "uninstall": [f"script/{TOKEN}", "uninstall", version]}


def write_cfg(cfg: Path, with_layer_line: bool = True, version: str = "v1") -> Path:
    layer = cfg / "layers" / "nimbus"
    (layer / "script").mkdir(parents=True, exist_ok=True)
    script = layer / "script" / TOKEN
    script.write_text(SCRIPT)
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    (cfg / "instructions.md").write_text("# Global\nbe deterministic\n\n"
                                         + (DIRECTIVE + "\n" if with_layer_line else ""))
    (cfg / "profile.json").write_text(json.dumps({"harnesses": ["claude"]}))
    (layer / "instructions.md").write_text(f"## {TOKEN}\nuse {TOKEN}\n")
    (layer / "services.json").write_text(json.dumps({"services": {TOKEN: spec(version)}}))
    return layer


def run(argv) -> tuple:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = agentsync.main(argv)
    return code, out.getvalue()


@contextlib.contextmanager
def sandbox_home():
    saved = os.environ.get("HOME")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp).resolve() / "home"
        home.mkdir()
        os.environ["HOME"] = str(home)
        try:
            yield home, Path(tmp).resolve() / "cfg"
        finally:
            os.environ["HOME"] = saved if saved is not None else ""
            if saved is None:
                del os.environ["HOME"]


def calls(layer: Path) -> list:
    log = layer / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def recorded(home: Path) -> dict:
    path = home / ".config/agentsync/managed.json"
    return json.loads(path.read_text()).get("services", {}) if path.exists() else {}


def traces(root: Path) -> list:
    return [str(p) for p in root.rglob("*")
            if p.is_file() and not p.is_symlink() and TOKEN in p.read_text(errors="replace")]


ARGS = ["--no-mcp-import"]


# --- unit -------------------------------------------------------------------------

def unit_declaration():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp).resolve() / "cfg"
        layer = write_cfg(cfg)
        found = declared(cfg)
        assert list(found) == [TOKEN]
        assert found[TOKEN]["install"] == [str(layer.resolve() / "script" / TOKEN), "install", "v1"]
        assert found[TOKEN]["uninstall"][0] == found[TOKEN]["install"][0]

        (layer / "services.json").write_text(json.dumps({"services": {TOKEN: {
            "install": ["launchctl", "load", "/abs/agent.plist"],
            "uninstall": ["/usr/bin/true"]}}}))
        found = declared(cfg)[TOKEN]
        assert found["install"] == ["launchctl", "load", "/abs/agent.plist"]
        assert found["uninstall"] == ["/usr/bin/true"], "bare and absolute commands stay as written"

        (cfg / "services.json").write_text(json.dumps({"services": {TOKEN: spec("v1")}}))
        try:
            declared(cfg)
        except LayerConflict as e:
            assert "services.json" in str(e) and TOKEN in str(e)
        else:
            raise AssertionError("a service name defined twice must be refused")
        (cfg / "services.json").unlink()

        for bad in ({"services": {"x": "oops"}},
                    {"services": {"x": {"install": ["a"]}}},
                    {"services": {"x": {"install": [], "uninstall": ["a"]}}},
                    {"services": {"x": {"install": ["a"], "uninstall": ["b", 3]}}}):
            (layer / "services.json").write_text(json.dumps(bad))
            try:
                declared(cfg)
            except ConfigError as e:
                assert "service x" in str(e) and "services.json" in str(e), str(e)
            else:
                raise AssertionError(f"malformed spec accepted: {bad}")

        (cfg / "instructions.md").write_text("# Global\n")
        assert declared(cfg) == {}, "a layer that is not included declares nothing"

        try:
            refuse_in_project({"x": {}})
        except ConfigError as e:
            assert "project" in str(e)
        else:
            raise AssertionError("project scope must refuse services")


# --- lifecycle --------------------------------------------------------------------

def lifecycle():
    with sandbox_home() as (home, cfg):
        layer = write_cfg(cfg)
        common = ["--config", str(cfg), *ARGS]

        code, out = run(["verify", *common])
        assert code == 1 and "not installed" in out, out
        assert calls(layer) == [], "verify must not execute anything"
        code, out = run(["diff", *common])
        assert code == 0 and "not installed" in out and calls(layer) == []

        assert run(["apply", *common])[0] == 0
        assert calls(layer) == ["install v1"], calls(layer)
        assert list(recorded(home).values())[0]["kind"] == "service"
        assert run(["verify", *common])[0] == 0
        assert run(["apply", *common])[0] == 0
        assert calls(layer) == ["install v1"], "an unchanged service must not run again"

        (layer / "services.json").write_text(json.dumps({"services": {TOKEN: spec("v2")}}))
        code, out = run(["verify", *common])
        assert code == 1 and "commands changed" in out and calls(layer) == ["install v1"]
        assert run(["apply", *common])[0] == 0
        assert calls(layer) == ["install v1", "uninstall v1", "install v2"], calls(layer)

        (cfg / "instructions.md").write_text("# Global\nbe deterministic\n\n")
        code, out = run(["verify", *common])
        assert code == 1 and "no longer declared" in out
        assert calls(layer)[-1] == "install v2", "verify must not execute anything"
        assert run(["apply", *common])[0] == 0
        assert calls(layer)[-1] == "uninstall v2", calls(layer)
        assert recorded(home) == {}
        assert not traces(home), f"the layer survived its directive: {traces(home)}"
        assert run(["verify", *common])[0] == 0
        assert run(["apply", *common])[0] == 0
        assert len(calls(layer)) == 4, "nothing left to run"


def failing_uninstall_keeps_the_record():
    with sandbox_home() as (home, cfg):
        layer = write_cfg(cfg)
        common = ["--config", str(cfg), *ARGS]
        assert run(["apply", *common])[0] == 0
        (layer / "refuse-uninstall").write_text("")
        (cfg / "instructions.md").write_text("# Global\n")

        code, out = run(["apply", *common])
        assert code == 1 and "uninstall failed" in out and "agent busy" in out, out
        assert len(recorded(home)) == 1, "a failed uninstall must keep the record"
        assert run(["apply", *common])[0] == 1, "the failed uninstall is retried"
        assert calls(layer).count("uninstall v1") == 2

        (layer / "refuse-uninstall").unlink()
        assert run(["apply", *common])[0] == 0
        assert recorded(home) == {}
        assert run(["apply", *common])[0] == 0 and calls(layer).count("uninstall v1") == 3


def failing_install_is_not_recorded():
    with sandbox_home() as (home, cfg):
        layer = write_cfg(cfg)
        (layer / "services.json").write_text(json.dumps({"services": {TOKEN: {
            "install": ["/nonexistent/program"], "uninstall": ["/usr/bin/true"]}}}))
        code, out = run(["apply", "--config", str(cfg), *ARGS])
        assert code == 1 and "install failed" in out, out
        assert recorded(home) == {}


def uninstall_verb_releases_everything():
    with sandbox_home() as (home, cfg):
        layer = write_cfg(cfg)
        common = ["--config", str(cfg), *ARGS]
        assert run(["apply", *common])[0] == 0
        assert run(["uninstall", *common])[0] == 0
        assert calls(layer) == ["install v1", "uninstall v1"]
        assert recorded(home) == {}


# --- scopes where nothing may run ---------------------------------------------------

def sandbox_root_and_project_never_execute():
    with sandbox_home() as (home, cfg):
        layer = write_cfg(cfg)
        other = home.parent / "other-root"
        code, out = run(["apply", "--config", str(cfg), "--root", str(other), *ARGS])
        assert code == 0 and "not managed outside the real home" in out, out
        assert calls(layer) == [] and recorded(other) == {}, \
            "a sandbox root must not run or record a service"
        assert run(["verify", "--config", str(cfg), "--root", str(other), *ARGS])[0] == 0

        proj = home.parent / "repo"
        write_cfg(proj / ".agentsync")
        try:
            run(["apply", "--project", str(proj)])
        except SystemExit as e:
            assert str(e.code).startswith("error: ") and "project config" in str(e.code), e.code
        else:
            raise AssertionError("project scope must refuse a declared service")
        assert calls(proj / ".agentsync" / "layers" / "nimbus") == []


def main():
    unit_declaration()
    lifecycle()
    failing_uninstall_keeps_the_record()
    failing_install_is_not_recorded()
    uninstall_verb_releases_everything()
    sandbox_root_and_project_never_execute()
    print("test_services: PASS")


if __name__ == "__main__":
    main()
