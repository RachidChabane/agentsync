"""Shared utilities for the agentsync reconciler and its adapters.

Mechanism only — no per-harness knowledge lives here. Adapters declare desired state;
these helpers converge a target file to it (apply) or report whether it already matches
(check / drift). Every helper is idempotent: a second `apply` is a no-op, and `check`
right after `apply` reports no drift. Stdlib only.
"""
from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

# Tiers hidden from the model's context (every harness but Claude collapses to this).
HIDDEN_TIERS = {"user-invocable-only", "off"}


@dataclass
class Ctx:
    """Everything an adapter needs: where sources live, where to write, the policy."""
    repo: Path          # this checkout (source of enforcement scripts, etc.)
    root: Path          # target root to write into (default: $HOME; a temp dir in tests)
    instructions: Path  # path to the rendered instructions markdown
    skills: dict        # skill name -> tier
    servers: dict       # MCP servers, single-source schema
    profile: dict       # which harnesses, optional overrides
    check: bool = False  # True = report drift, write nothing

    @property
    def enforce_dir(self) -> Path:
        return self.repo / "core" / "enforcement"


@dataclass
class Report:
    name: str
    lines: list = field(default_factory=list)   # (status, message)
    drift: bool = False

    def ok(self, m):     self.lines.append(("ok", m))
    def wrote(self, m):  self.lines.append(("write", m))
    def linked(self, m): self.lines.append(("link", m))
    def skipped(self, m): self.lines.append(("skip", m))
    def diff(self, m):   self.drift = True; self.lines.append(("drift", m))


# ----- platform-aware target paths -------------------------------------------------

def vscode_user_dir(root: Path) -> Path:
    """VS Code's per-user settings dir differs by OS."""
    if platform.system() == "Darwin":
        return root / "Library" / "Application Support" / "Code" / "User"
    if platform.system() == "Windows":  # pragma: no cover - best effort
        return root / "AppData" / "Roaming" / "Code" / "User"
    return root / ".config" / "Code" / "User"   # Linux


# ----- filesystem convergence helpers ----------------------------------------------

def load_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def _backup(path: Path) -> Path:
    """Move an existing real file out of the way without ever clobbering a prior backup."""
    bak = path.with_name(path.name + ".bak")
    n = 2
    while bak.exists():
        bak = path.with_name(f"{path.name}.bak{n}")
        n += 1
    path.rename(bak)
    return bak


def write_text(path: Path, content: str, ctx: Ctx, rep: Report, label: str):
    cur = path.read_text() if path.exists() and not path.is_symlink() else None
    if cur == content:
        rep.ok(f"{label}: {path}")
        return
    if ctx.check:
        rep.diff(f"{label}: {path} would change")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    path.write_text(content)
    rep.wrote(f"{label}: {path}")


def write_json(path: Path, obj, ctx: Ctx, rep: Report, label: str):
    write_text(path, json.dumps(obj, indent=2) + "\n", ctx, rep, label)


def symlink(path: Path, target: Path, ctx: Ctx, rep: Report, label: str):
    tgt = str(target)
    if path.is_symlink() and os.readlink(path) == tgt:
        rep.ok(f"{label}: {path}")
        return
    if ctx.check:
        rep.diff(f"{label}: {path} -> {tgt} not linked")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        _backup(path)
    os.symlink(tgt, path)
    rep.linked(f"{label}: {path} -> {tgt}")


def merge_json(path: Path, mutate, ctx: Ctx, rep: Report, label: str):
    """Apply `mutate(dict)` to the file's JSON (or {}), preserving everything else.

    Drift = our managed mutation would change the file. Because `mutate` is idempotent,
    a file we already own reports no drift; one a user reverted reports drift. This is
    exactly "is our managed state present and correct?" — not "did anything change?".
    """
    cur = load_json(path) or {}
    desired = json.loads(json.dumps(cur))  # deep copy
    mutate(desired)
    if desired == cur:
        rep.ok(f"{label}: {path}")
        return
    if ctx.check:
        rep.diff(f"{label}: {path} managed keys differ")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    path.write_text(json.dumps(desired, indent=2) + "\n")
    rep.wrote(f"{label}: {path}")


def ensure_command_hook(hooks: dict, event: str, command: str, matcher: str | None = None,
                        key: str = "command"):
    """Idempotently add a command hook to a Claude/Copilot-style hooks block.

    Matches by the command/bash string so re-applying never duplicates. `key` is
    "command" (Claude) or "bash" (Copilot). For Copilot, matcher/timeout go flat on the
    entry; for Claude they nest under a group with a "hooks" array.
    """
    arr = hooks.setdefault(event, [])
    for entry in arr:
        if entry.get(key) == command:                       # flat (Copilot) already there
            return
        for h in entry.get("hooks", []):                    # nested (Claude) already there
            if h.get("command") == command:
                return
    e: dict
    if key == "bash":                                       # Copilot flat schema
        e = {"type": "command", "bash": command, "timeoutSec": 130}
    else:                                                   # Claude nested schema
        e = {"hooks": [{"type": "command", "command": command}]}
    if matcher:
        e["matcher"] = matcher
    arr.append(e)
