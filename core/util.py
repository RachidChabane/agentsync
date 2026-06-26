"""Shared types + low-level helpers for the reconciler. Mechanism only — no per-harness
knowledge. The convergence logic lives in targets.py; this holds the context, the
per-run report, platform paths, and filesystem primitives. Stdlib only.
"""
from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field
from pathlib import Path

# Tiers hidden from the model's context (every harness but Claude collapses to this).
HIDDEN_TIERS = {"user-invocable-only", "off"}


@dataclass
class Ctx:
    repo: Path          # this checkout (source of enforcement scripts)
    root: Path          # target root (default $HOME; a temp dir in tests)
    instructions: Path  # rendered instructions markdown
    skills: dict        # skill name -> tier
    servers: dict       # MCP servers, single-source schema
    profile: dict       # harnesses + options
    verb: str = "apply"  # apply | verify | diff | uninstall

    @property
    def check(self) -> bool:
        return self.verb in ("verify", "diff")

    @property
    def enforce_dir(self) -> Path:
        return self.repo / "core" / "enforcement"


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


def backup_once(path: Path):
    """Snapshot the original (pre-agentsync) file ONCE, so uninstall can restore it.
    Never overwrites an existing .bak — the first snapshot is the true original."""
    bak = path.with_name(path.name + ".bak")
    if not bak.exists() and path.exists() and not path.is_symlink():
        bak.write_text(path.read_text())
    return bak


def dump(obj) -> str:
    return json.dumps(obj, indent=2) + "\n"
