#!/usr/bin/env python3
"""agentsync reconciler — one declarative config, rendered into every AI coding harness.

  python3 -m core.agentsync apply     [--root DIR] [--config DIR] [--harness N ...]
  python3 -m core.agentsync verify    [...]   # read-only drift check, exit 1 on drift
  python3 -m core.agentsync diff      [...]   # preview the exact change (no writes)
  python3 -m core.agentsync uninstall [...]   # remove only what agentsync added

Mechanism only: loads the config, then asks each enabled adapter for its targets and
interprets them for the verb. Adapters hold all per-harness knowledge. Idempotent.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path

from core import skills as skillmod
from core.adapters import ADAPTERS
from core.targets import ClaudeMcp, Link
from core.util import Ctx, Report

REPO = Path(__file__).resolve().parents[1]
ICON = {"ok": "·", "write": "✎", "link": "→", "skip": "–", "remove": "✗", "drift": "Δ"}


def load_config(config_dir: Path):
    def jload(name):
        p = config_dir / name
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError as e:
            sys.exit(f"error: {p} is not valid JSON ({e})")
    return (jload("profile.json"), jload("skills.json").get("skills", {}),
            jload("mcp.json").get("servers", {}), jload("overrides.json"))


def _installed(name: str, root: Path) -> bool:
    probes = {
        "claude": [root / ".claude", "claude"],
        "copilot": [root / ".copilot", "copilot"],
        "opencode": [root / ".config/opencode", "opencode"],
        "vscode": [root / "Library/Application Support/Code", root / ".config/Code", "code"],
    }
    for p in probes.get(name, []):
        if isinstance(p, Path) and p.exists():
            return True
        if isinstance(p, str) and shutil.which(p):
            return True
    return False


def doctor(ctx: Ctx, wanted: list) -> int:
    ok = True
    print("environment:")
    for tool in ("python3", "git", "bash"):
        print(f"  {'·' if shutil.which(tool) else '✗'} {tool}")
        ok = ok and bool(shutil.which(tool))
    runners = [r for r in ("make", "mise", "just", "npm") if shutil.which(r)]
    print(f"  task runners: {', '.join(runners) or 'NONE (determinism gate fails open everywhere)'}")
    binp = str(Path.home() / ".local/bin") in os.environ.get("PATH", "").split(os.pathsep)
    print(f"  {'·' if binp else '–'} ~/.local/bin on PATH")
    for cli in ("agentsync", "scaffold-determinism"):
        print(f"  {'·' if shutil.which(cli) else '–'} {cli} on PATH")

    print("harnesses:")
    for name, a in ADAPTERS.items():
        inst, en = _installed(name, ctx.root), name in wanted
        flag = "·" if inst and en else ("!" if en and not inst else "–")
        print(f"  {flag} {name:9} installed={str(inst):5} enabled={str(en):5} "
              f"caps={','.join(sorted(a.capabilities()))}")
        if en and not inst:
            ok = False

    miss = []
    for n, s in ctx.servers.items():
        auth = s.get("auth", {})
        if auth.get("env") and not os.environ.get(auth["env"]):
            miss.append(f"{n}: env ${auth['env']} not set")
        hh = auth.get("headersHelper")
        if hh and not Path(hh).expanduser().exists():
            miss.append(f"{n}: headersHelper missing ({hh})")
    if miss:
        ok = False
        print("mcp auth gaps:")
        for m in miss:
            print(f"  ✗ {m}")

    vctx = replace(ctx, verb="verify")
    drift = any(run_adapter(ADAPTERS[h], vctx, no_mcp_import=False).drift for h in wanted)
    print(f"sync: {'changes pending — run `agentsync apply`' if drift else 'in sync with config'}")

    broken = [t.path for h in wanted for t in ADAPTERS[h].targets(ctx)
              if isinstance(t, Link) and not Path(t.src).exists()]
    if broken:
        ok = False
        print("broken links (source missing):")
        for b in broken:
            print(f"  ✗ {b}")

    print("\n" + ("ok: healthy." if ok and not drift else "see items above."))
    return 0 if ok else 1


def run_adapter(adapter, ctx: Ctx, no_mcp_import: bool) -> Report:
    rep = Report(adapter.name)
    for t in adapter.targets(ctx):
        if no_mcp_import and isinstance(t, ClaudeMcp):
            continue
        t.process(ctx, rep)
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agentsync")
    ap.add_argument("command", choices=["apply", "verify", "diff", "uninstall", "doctor"])
    ap.add_argument("--root", help="target root to write into (default: $HOME)")
    ap.add_argument("--config", help="config dir (default: ./config, else ./config.example)")
    ap.add_argument("--harness", action="append", help="limit to these harnesses (repeatable)")
    ap.add_argument("--no-mcp-import", action="store_true", help="skip the Claude MCP CLI import")
    args = ap.parse_args(argv)

    config_dir = Path(args.config) if args.config else (
        REPO / "config" if (REPO / "config").exists() else REPO / "config.example")
    profile, skills_cfg, servers, overrides = load_config(config_dir)

    root = Path(args.root).expanduser() if args.root else \
        Path(profile["root"]).expanduser() if profile.get("root") else Path.home()
    wanted = args.harness or profile.get("harnesses", list(ADAPTERS))
    unknown = [h for h in wanted if h not in ADAPTERS]
    if unknown:
        sys.exit(f"unknown harness(es): {', '.join(unknown)} (known: {', '.join(ADAPTERS)})")
    norm = skillmod.normalize(skills_cfg)
    skill_paths = skillmod.resolve(norm, root / ".cache/agentsync/skills",
                                   do_fetch=(args.command == "apply"))
    ctx = Ctx(repo=REPO, root=root, instructions=config_dir / "instructions.md",
              skills=skillmod.tiers(norm), servers=servers, profile=profile,
              verb=args.command, skill_paths=skill_paths, overrides=overrides)

    if args.command == "doctor":
        return doctor(ctx, wanted)
    if "vscode" in wanted and "claude" not in wanted:
        print("warning: vscode's commit gate reuses Claude's hooks — enable 'claude' too "
              "or vscode has no gate.\n", file=sys.stderr)

    print(f"{args.command}: config={config_dir.name} root={root} harnesses={','.join(wanted)}\n")
    reports = [run_adapter(ADAPTERS[h], ctx, args.no_mcp_import) for h in wanted]

    drift = False
    for rep in reports:
        print(f"[{rep.name}]")
        for status, msg in rep.lines:
            print(f"  {ICON.get(status, '?')} {msg}")
        drift = drift or rep.drift
    if args.command == "diff":
        blocks = [b for rep in reports for b in rep.diffs]
        if blocks:
            print("\n--- pending changes ---")
            print("".join(blocks))
    print()

    if args.command == "verify":
        print("DRIFT — run `apply` to converge." if drift else "ok: all harnesses match config.")
        return 1 if drift else 0
    if args.command == "diff":
        print("changes pending — run `apply`." if drift else "nothing to change.")
        return 0
    print("done." if args.command == "apply" else "uninstalled (originals restored from .bak where present).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
