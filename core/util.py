"""Shared types + low-level helpers for the reconciler. Mechanism only — no per-harness
knowledge. The convergence logic lives in targets.py; this holds the context, the
per-run report, platform paths, and filesystem primitives. Stdlib only.
"""
from __future__ import annotations

import copy
import json
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

# Tiers hidden from the model's context (every harness but Claude collapses to this).
HIDDEN_TIERS = {"user-invocable-only", "off"}

# agentsync's own state under the target root: user scope keeps it beside its other
# artifacts; project scope keeps it in the repo's agentsync dir, next to the config.
USER_STATE_DIR = Path(".config") / "agentsync"
PROJECT_STATE_DIR = Path(".agentsync")
LEDGER_FILE = "originals.json"
LEDGER_KEY = "captured"
RECORD_FILE = "managed.json"


class ConfigError(ValueError):
    """A config that cannot be rendered as written; the message names where and why."""


@dataclass
class Ctx:
    repo: Path          # this checkout (source of enforcement scripts)
    root: Path          # target root (default $HOME; a temp dir in tests)
    config: Path        # the config dir (holds instructions/skills/mcp/overrides + docs/)
    instructions: Path  # shared instructions source (may hold @include lines)
    skills: dict        # skill name -> tier spec (string, or harness -> tier map)
    servers: dict       # MCP servers, single-source schema
    profile: dict       # harnesses + options
    verb: str = "apply"  # apply | verify | diff | uninstall
    scope: str = "user"  # user ($HOME) | project (a repo; committed, team-shared files)
    skill_paths: dict = field(default_factory=dict)  # name -> resolved dir (or None)
    overrides: dict = field(default_factory=dict)    # harness -> extra settings keys

    def tiers_for(self, harness: str) -> dict:
        """skill name -> the tier this harness sees."""
        from .skills import tiers_for
        return tiers_for(self.skills, harness)

    @property
    def check(self) -> bool:
        return self.verb in ("verify", "diff")

    @property
    def state_dir(self) -> Path:
        return self.root / (PROJECT_STATE_DIR if self.scope == "project" else USER_STATE_DIR)

    @property
    def ledger(self) -> "OriginalsLedger":
        return OriginalsLedger(self.state_dir / LEDGER_FILE, self.root)

    @property
    def record(self) -> "ManagedRecord":
        return ManagedRecord(self.state_dir / RECORD_FILE, self.root)

    @property
    def enforce_dir(self) -> Path:
        return self.repo / "core" / "enforcement"

    @property
    def enforcement(self) -> bool:
        """Determinism-protocol enforcement (gate + nudge/plugin) is opt-out via
        profile.json {"enforcement": false} — config sync alone stays available."""
        return bool(self.profile.get("enforcement", True))


@dataclass
class Report:
    name: str
    lines: list = field(default_factory=list)   # (status, message)
    drift: bool = False
    diffs: list = field(default_factory=list)   # human-readable diff blocks

    def ok(self, m):     self.lines.append(("ok", m))
    def wrote(self, m):  self.lines.append(("write", m))
    def linked(self, m): self.lines.append(("link", m))
    def skipped(self, m): self.lines.append(("skip", m))
    def removed(self, m): self.lines.append(("remove", m))
    def diff(self, m):   self.drift = True; self.lines.append(("drift", m))


def vscode_user_dir(root: Path) -> Path:
    if platform.system() == "Darwin":
        return root / "Library" / "Application Support" / "Code" / "User"
    if platform.system() == "Windows":  # pragma: no cover
        return root / "AppData" / "Roaming" / "Code" / "User"
    return root / ".config" / "Code" / "User"


def load_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


class OriginalsLedger:
    """Paths whose pre-agentsync original has been captured: as a `.bak` when a real
    file was there, as nothing when the path was absent or a symlink. Capture happens
    on first contact only, so a file agentsync wrote itself is never later mistaken for
    an original (and restored over the user's state on uninstall). Paths are stored
    relative to the target root, so a project-scope ledger is valid on every checkout."""

    def __init__(self, store: Path, root: Path):
        self.store, self.root = store, root

    def _key(self, path: Path) -> str:
        return os.path.relpath(path, self.root)

    def _load(self) -> set:
        return set((load_json(self.store) or {}).get(LEDGER_KEY, []))

    def _save(self, keys: set):
        if keys:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            self.store.write_text(dump({LEDGER_KEY: sorted(keys)}))
        elif self.store.exists():
            self.store.unlink()

    def captured(self, path: Path) -> bool:
        return self._key(path) in self._load()

    def record(self, path: Path):
        keys = self._load()
        if self._key(path) not in keys:
            self._save(keys | {self._key(path)})

    def forget(self, path: Path):
        keys = self._load()
        if self._key(path) in keys:
            self._save(keys - {self._key(path)})


class ManagedRecord:
    """What each adapter put in place on its last apply: per path, the target kind and
    exactly what it managed there (a link's source, a merged file's owned key paths and
    hooks). The next run releases whatever the config no longer asks for — and only
    that, so content agentsync never wrote is never touched. Paths are relative to the
    target root; layout: {adapter: {path: entry}}."""

    def __init__(self, store: Path, root: Path):
        self.store, self.root = store, root

    def _load(self) -> dict:
        return load_json(self.store) or {}

    def _key(self, path: Path) -> str:
        return os.path.relpath(path, self.root)

    def entry(self, path: Path) -> dict | None:
        """The entry any adapter recorded for `path` (a path has one owner shape)."""
        key = self._key(path)
        return next((paths[key] for paths in self._load().values() if key in paths), None)

    def owned_by(self, adapter: str) -> dict:
        """Absolute path -> entry, for everything `adapter` recorded."""
        return {self.root / k: v for k, v in self._load().get(adapter, {}).items()}

    def replace(self, adapter: str, entries: dict):
        """Set `adapter`'s whole record (absolute path -> entry); empty forgets it."""
        data = self._load()
        before = copy.deepcopy(data)
        if entries:
            data[adapter] = {self._key(p): e for p, e in sorted(entries.items())}
        else:
            data.pop(adapter, None)
        if data == before:
            return
        if data:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            self.store.write_text(dump(data))
        elif self.store.exists():
            self.store.unlink()


def backup_once(path: Path, ledger: OriginalsLedger):
    """Capture the original (pre-agentsync) file on first contact, so uninstall can
    restore it. Never overwrites an existing .bak, and never snapshots a path already
    captured — by then the file on disk is agentsync's own rendering."""
    if ledger.captured(path):
        return
    bak = path.with_name(path.name + ".bak")
    if not bak.exists() and path.exists() and not path.is_symlink():
        bak.write_text(path.read_text())
    ledger.record(path)


def dump(obj) -> str:
    return json.dumps(obj, indent=2) + "\n"
