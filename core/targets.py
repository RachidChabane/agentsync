"""Declarative targets: each adapter describes *what it manages* as a list of these, and
the reconciler interprets them for every verb — apply (converge), verify (drift), diff
(preview the exact change), uninstall (surgically remove only what we added). One
description, five behaviours; adapters hold no imperative I/O.

All convergence is idempotent: re-apply is a no-op, verify right after apply is clean,
and uninstall removes our keys/hooks/files while leaving the user's untouched.
"""
from __future__ import annotations

import copy
import difflib
import os
import subprocess
from pathlib import Path

from .util import Ctx, Report, backup_once, dump, load_json


def _udiff(name: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(keepends=True),
                                        new.splitlines(keepends=True),
                                        fromfile=f"a/{name}", tofile=f"b/{name}")) or ""


def set_path(d: dict, path: tuple, value):
    for k in path[:-1]:
        d = d.setdefault(k, {})
    d[path[-1]] = value


def del_path(d: dict, path: tuple):
    """Delete the leaf, then prune any ancestor dict left empty (so we don't orphan an
    empty `permission: {}` we created, but keep one that still holds the user's keys)."""
    stack, cur = [], d
    for k in path[:-1]:
        if not isinstance(cur, dict) or k not in cur:
            return
        stack.append((cur, k)); cur = cur[k]
    if isinstance(cur, dict):
        cur.pop(path[-1], None)
    for parent, k in reversed(stack):
        if isinstance(parent[k], dict) and not parent[k]:
            del parent[k]


class Target:
    label = ""
    def describe(self) -> str: return self.label
    def process(self, ctx: Ctx, rep: Report): raise NotImplementedError

    def _pending(self, ctx, rep, msg, name="", old="", new=""):
        rep.diff(msg)
        if ctx.verb == "diff" and (old or new):
            block = _udiff(name, old, new)
            if block:
                rep.diffs.append(block)


class Link(Target):
    def __init__(self, path: Path, src: Path, label: str):
        self.path, self.src, self.label = path, src, label

    def process(self, ctx, rep):
        want = str(self.src)
        cur = os.readlink(self.path) if self.path.is_symlink() else None
        if ctx.verb == "uninstall":
            if cur == want:
                self.path.unlink()
                bak = self.path.with_name(self.path.name + ".bak")
                if bak.exists():
                    bak.replace(self.path)
                rep.removed(f"{self.label}: {self.path}")
            else:
                rep.skipped(f"{self.label}: {self.path} not ours")
            return
        if cur == want:
            rep.ok(f"{self.label}: {self.path}")
            return
        if ctx.check:
            self._pending(ctx, rep, f"{self.label}: {self.path} -> {want} not linked")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            self.path.unlink()
        elif self.path.exists():
            backup_once(self.path); self.path.unlink()
        os.symlink(want, self.path)
        rep.linked(f"{self.label}: {self.path} -> {want}")


class Json(Target):
    """A file agentsync owns wholesale (e.g. an MCP artifact)."""
    def __init__(self, path: Path, obj, label: str):
        self.path, self.obj, self.label = path, obj, label

    def process(self, ctx, rep):
        new = dump(self.obj)
        cur = self.path.read_text() if self.path.exists() and not self.path.is_symlink() else None
        if ctx.verb == "uninstall":
            if self.path.exists():
                self.path.unlink()
                bak = self.path.with_name(self.path.name + ".bak")
                if bak.exists():
                    bak.replace(self.path)
                rep.removed(f"{self.label}: {self.path}")
            return
        if cur == new:
            rep.ok(f"{self.label}: {self.path}")
            return
        if ctx.check:
            self._pending(ctx, rep, f"{self.label}: {self.path} would change",
                          self.path.name, cur or "", new)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        backup_once(self.path)
        if self.path.is_symlink():
            self.path.unlink()
        self.path.write_text(new)
        rep.wrote(f"{self.label}: {self.path}")


class HookSpec:
    """One command hook, identified by a stable `marker` (the script basename) so an
    entry left behind after the repo moves is recognised and replaced, not duplicated."""
    def __init__(self, event, command, marker, matcher=None, key="command"):
        self.event, self.command, self.marker = event, command, marker
        self.matcher, self.key = matcher, key

    def entry(self) -> dict:
        if self.key == "bash":
            e: dict = {"type": "command", "bash": self.command, "timeoutSec": 130}
        else:
            e = {"hooks": [{"type": "command", "command": self.command}]}
        if self.matcher:
            e["matcher"] = self.matcher
        return e

    def _mine(self, entry: dict) -> bool:
        if self.marker in (entry.get("command") or "") or self.marker in (entry.get("bash") or ""):
            return True
        return any(self.marker in (h.get("command") or "") for h in entry.get("hooks", []))

    def sync(self, hooks_block: dict):
        arr = hooks_block.setdefault(self.event, [])
        mine = [e for e in arr if self._mine(e)]
        if len(mine) == 1 and mine[0] == self.entry():
            return  # already correct — idempotent no-op
        arr[:] = [e for e in arr if not self._mine(e)] + [self.entry()]

    def strip(self, hooks_block: dict):
        if self.event in hooks_block:
            hooks_block[self.event][:] = [e for e in hooks_block[self.event] if not self._mine(e)]


class Merge(Target):
    """A file shared with the user. We own specific key-paths (replaced wholesale) and
    specific hooks (kept exactly-once); everything else is preserved."""
    def __init__(self, path: Path, owned: list, hooks: list, label: str):
        self.path, self.owned, self.hooks, self.label = path, owned, hooks, label

    def _desired(self, cur: dict) -> dict:
        d = copy.deepcopy(cur)
        for path, value in self.owned:
            set_path(d, path, value)
        if self.hooks:
            hb = d.setdefault("hooks", {})
            for spec in self.hooks:
                spec.sync(hb)
        return d

    def _without(self, cur: dict) -> dict:
        d = copy.deepcopy(cur)
        for path, _ in self.owned:
            del_path(d, path)
        hb = d.get("hooks", {})
        for spec in self.hooks:
            spec.strip(hb)
        for ev in [k for k, v in hb.items() if not v]:
            del hb[ev]
        if "hooks" in d and not d["hooks"]:
            del d["hooks"]
        return d

    def process(self, ctx, rep):
        cur = load_json(self.path) or {}
        target = self._without(cur) if ctx.verb == "uninstall" else self._desired(cur)
        if target == cur:
            (rep.skipped if ctx.verb == "uninstall" else rep.ok)(f"{self.label}: {self.path}")
            return
        if ctx.check:
            self._pending(ctx, rep, f"{self.label}: {self.path} managed keys differ",
                          self.path.name, dump(cur), dump(target))
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        backup_once(self.path)
        if self.path.is_symlink():
            self.path.unlink()
        self.path.write_text(dump(target))
        (rep.removed if ctx.verb == "uninstall" else rep.wrote)(f"{self.label}: {self.path}")


class ClaudeMcp(Target):
    """Claude's user-scope MCP can't be symlinked (stateful ~/.claude.json), so import via
    the CLI. Idempotent: a sidecar records the imported set; unchanged => no CLI churn;
    dropped servers are pruned. Skipped unless writing into the real $HOME with the CLI."""
    label = "mcp-import"

    def __init__(self, servers: dict, root: Path):
        self.servers, self.sidecar = servers, root / ".claude" / ".agentsync-mcp.json"
        self.root = root

    def _prev(self) -> dict:
        return load_json(self.sidecar) or {}

    def process(self, ctx, rep):
        import shutil
        have_cli = bool(shutil.which("claude"))
        manageable = ctx.root == Path.home() and have_cli
        prev = self._prev()
        if ctx.check:
            if not manageable:
                rep.skipped("mcp-import: not manageable here (sandbox or no `claude` CLI)")
            elif prev != self.servers:
                self._pending(ctx, rep, "mcp-import: Claude MCP servers differ",
                              "claude-mcp", dump(prev), dump(self.servers))
            else:
                rep.ok("mcp-import: up to date")
            return
        if ctx.verb == "uninstall":
            if have_cli:
                for name in prev:
                    subprocess.run(["claude", "mcp", "remove", name, "-s", "user"], capture_output=True)
            if self.sidecar.exists():
                self.sidecar.unlink()
            rep.removed("mcp-import: removed Claude MCP servers")
            return
        # apply
        if ctx.root != Path.home() or not have_cli:
            rep.skipped("mcp-import: sandbox or no `claude` CLI — artifact written, import skipped")
            return
        if prev == self.servers:
            rep.ok("mcp-import: up to date")
            return
        for name in set(prev) - set(self.servers):
            subprocess.run(["claude", "mcp", "remove", name, "-s", "user"], capture_output=True)
            rep.removed(f"mcp-import: prune {name}")
        for name, spec in self.servers.items():
            subprocess.run(["claude", "mcp", "remove", name, "-s", "user"], capture_output=True)
            r = subprocess.run(["claude", "mcp", "add-json", name, dump(spec).strip(), "-s", "user"],
                               capture_output=True)
            (rep.wrote if r.returncode == 0 else rep.skipped)(f"mcp-import: {name}")
        self.sidecar.parent.mkdir(parents=True, exist_ok=True)
        self.sidecar.write_text(dump(self.servers))
