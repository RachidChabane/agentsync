"""Services: background jobs a config (or one of its layers) keeps installed.

A service is declared by two commands in `services.json`, in the config dir or in a
layer:

    {"services": {"sync-agent": {"install":   ["script/sync-agent", "install"],
                                 "uninstall": ["script/sync-agent", "uninstall"]}}}

A command whose first word holds a slash is resolved against the directory of the file
that declares it, so a layer carries its own scripts. The commands own the job itself (a
LaunchAgent, a cron entry, a daemon): the engine only decides *when* each one runs.

- `apply` runs `install` for a service that is not recorded yet, or whose commands
  changed (the recorded `uninstall` runs first). An unchanged service is left alone, so
  a job that acts at load time does not fire on every apply.
- A recorded service the config no longer declares has its recorded `uninstall` run on
  the next `apply`; `uninstall` runs it for all of them. A command that fails keeps the
  record, so the next run retries, and the run exits non-zero.
- `verify` and `diff` execute nothing: they compare what is declared with what is
  recorded and report the difference as drift.
- Commands run only against the real home. A sandbox root, and project scope (where a
  shared repo must not decide what runs on a machine), never execute or record anything.

The record lives in `managed.json`, like every other thing the engine puts in place.
Stdlib only.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from .instructions import layers
from .layers import load_json_source, merge_named
from .util import ConfigError, Ctx, Report

SERVICES_FILE, SERVICES_KEY = "services.json", "services"
INSTALL_KEY, UNINSTALL_KEY = "install", "uninstall"
COMMAND_KEYS = (INSTALL_KEY, UNINSTALL_KEY)
RECORD_OWNER = "services"
RECORD_KIND = "service"
COMMAND_TIMEOUT_SECONDS = 120
FAILURE_DETAIL_CHARS = 400

Runner = Callable[[list], "tuple[bool, str]"]


def run_command(argv: list) -> tuple:
    """(succeeded, detail): the command's exit status and the tail of what it printed."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              timeout=COMMAND_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    detail = (done.stdout + done.stderr).strip()[-FAILURE_DETAIL_CHARS:]
    return done.returncode == 0, detail


def _resolve_command(argv: list, base: Path) -> list:
    head, *rest = argv
    if "/" in head and not Path(head).is_absolute():
        head = str((base / head).resolve())
    return [head, *rest]


def _entry(name: str, spec, base: Path, source: Path) -> dict:
    where = f"{source}: service {name}"
    if not isinstance(spec, dict):
        raise ConfigError(f"{where} must be an object with {' and '.join(COMMAND_KEYS)}")
    entry = {"kind": RECORD_KIND}
    for key in COMMAND_KEYS:
        argv = spec.get(key)
        if not (isinstance(argv, list) and argv and all(isinstance(a, str) and a for a in argv)):
            raise ConfigError(f"{where}: {key} must be a non-empty list of strings")
        entry[key] = _resolve_command(argv, base)
    return entry


def declared(config_dir: Path) -> dict:
    """name -> entry for every service the config dir and its included layers declare."""
    services: dict = {}
    for base in (config_dir.resolve(), *layers(config_dir)):
        source = base / SERVICES_FILE
        found = {name: _entry(name, spec, base, source)
                 for name, spec in load_json_source(source).get(SERVICES_KEY, {}).items()}
        services = merge_named(services, found, "services", source)
    return services


def refuse_in_project(services: dict) -> None:
    if services:
        raise ConfigError(f"{SERVICES_FILE}: services run commands on this machine, so a "
                          f"project config may not declare them ({', '.join(sorted(services))})")


def _record_path(ctx: Ctx, name: str) -> Path:
    """A service has no file; the record keeps its usual path-keyed layout under the
    state dir."""
    return ctx.state_dir / RECORD_OWNER / name


def reconcile(ctx: Ctx, services: dict, run: Runner = run_command) -> Report:
    rep = Report(RECORD_OWNER)
    recorded = ctx.record.owned_by(RECORD_OWNER)
    wanted = {_record_path(ctx, name): entry for name, entry in services.items()}
    if not (wanted or recorded):
        return rep
    if ctx.scope != "user" or ctx.root != Path.home():
        rep.skipped("services: not managed outside the real home")
        return rep
    if ctx.check:
        _report_drift(rep, recorded, wanted)
    elif ctx.verb == "uninstall":
        ctx.record.replace(RECORD_OWNER, _release_all(rep, recorded, run))
    else:
        ctx.record.replace(RECORD_OWNER, _converge(rep, recorded, wanted, run))
    return rep


def _report_drift(rep: Report, recorded: dict, wanted: dict) -> None:
    for path, entry in wanted.items():
        if path not in recorded:
            rep.diff(f"service {path.name}: not installed")
        elif recorded[path] != entry:
            rep.diff(f"service {path.name}: commands changed")
        else:
            rep.ok(f"service {path.name}")
    for path in recorded.keys() - wanted.keys():
        rep.diff(f"service {path.name}: no longer declared")


def _converge(rep: Report, recorded: dict, wanted: dict, run: Runner) -> dict:
    kept = _release_all(rep, {p: e for p, e in recorded.items() if p not in wanted}, run)
    kept.update({p: e for p, e in recorded.items() if p in wanted})
    for path, entry in wanted.items():
        have = recorded.get(path)
        if have == entry:
            rep.ok(f"service {path.name}")
            continue
        if have is not None and not _execute(rep, path, have[UNINSTALL_KEY], "uninstall", run):
            continue
        kept.pop(path, None)
        if _execute(rep, path, entry[INSTALL_KEY], "install", run):
            kept[path] = entry
            rep.wrote(f"service {path.name}: installed")
    return kept


def _release_all(rep: Report, recorded: dict, run: Runner) -> dict:
    """The entries whose uninstall failed; everything else is released."""
    kept = {}
    for path, entry in recorded.items():
        if _execute(rep, path, entry[UNINSTALL_KEY], "uninstall", run):
            rep.removed(f"service {path.name}: uninstalled")
        else:
            kept[path] = entry
    return kept


def _execute(rep: Report, path: Path, argv: list, what: str, run: Runner) -> bool:
    succeeded, detail = run(argv)
    if not succeeded:
        rep.fail(f"service {path.name}: {what} failed ({' '.join(argv)}): {detail}")
    return succeeded

