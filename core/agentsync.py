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

from core import __version__
from core import gen_docs
from core import skills as skillmod
from core.adapters import ADAPTERS
from core.targets import ClaudeMcp, Link
from core.util import Ctx, Report

REPO = Path(__file__).resolve().parents[1]
ICON = {"ok": "·", "write": "✎", "link": "→", "skip": "–", "remove": "✗", "drift": "Δ"}


def resolve_config(arg: str | None, repo: Path) -> Path:
    """--config wins; else the repo's config/, else config.example/, else the user-scope
    dir (~/.config/agentsync) so a pipx/uvx install works without a checkout."""
    if arg:
        return Path(arg).expanduser()
    for cand in (repo / "config", repo / "config.example"):
        if cand.exists():
            return cand
    fallback = Path.home() / ".config" / "agentsync"
    if fallback.exists():
        return fallback
    sys.exit(f"error: no config found — create {fallback} (see config.example/ in the "
             "repo) or pass --config DIR")


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
        "cursor": [root / ".cursor", "cursor"],
        "windsurf": [root / ".codeium/windsurf", "windsurf"],
        "zed": [root / ".config/zed", "zed"],
        "cline": [root / ".cline", root / "Documents/Cline", "cline"],
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
    tgts = adapter.project_targets(ctx) if ctx.scope == "project" else adapter.targets(ctx)
    if ctx.scope == "project" and not tgts:
        rep.skipped("no project-scope surface")
        return rep
    for t in tgts:
        if no_mcp_import and isinstance(t, ClaudeMcp):
            continue
        t.process(ctx, rep)
    return rep


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["pack"]:  # sibling concern: plugin packaging (needs no config dir)
        from core import plugpack
        return plugpack.main(argv[1:])
    ap = argparse.ArgumentParser(
        prog="agentsync",
        epilog="other commands: pack SRC [--out DIR] [--check] — package a plugin "
               "bundle into Claude Code + Copilot plugin trees (agentsync pack --help)")
    ap.add_argument("--version", action="version", version=f"agentsync {__version__}")
    ap.add_argument("command", choices=["apply", "verify", "diff", "uninstall", "doctor", "docs"])
    ap.add_argument("--root", help="target root to write into (default: $HOME)")
    ap.add_argument("--config", help="config dir (default: ./config, else ./config.example)")
    ap.add_argument("--harness", action="append", help="limit to these harnesses (repeatable)")
    ap.add_argument("--no-mcp-import", action="store_true", help="skip the Claude MCP CLI import")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable output (verify/diff only); exit codes unchanged")
    ap.add_argument("--project", nargs="?", const=".", metavar="DIR",
                    help="project scope: render committed, team-shared files into this "
                         "repo (config read from DIR/.agentsync)")
    args = ap.parse_args(argv)
    if args.json and args.command not in ("verify", "diff"):
        ap.error("--json is only supported with verify and diff")
    if args.project and args.command in ("doctor", "docs"):
        ap.error(f"--project is not supported with {args.command}")

    proj = Path(args.project).expanduser().resolve() if args.project else None
    if proj:
        config_dir = Path(args.config).expanduser() if args.config else proj / ".agentsync"
        if not config_dir.is_dir():
            sys.exit(f"error: {config_dir} not found — create it (instructions.md, mcp.json, "
                     "profile.json) to make this repo agentsync-managed")
    else:
        config_dir = resolve_config(args.config, REPO)
    profile, skills_cfg, servers, overrides = load_config(config_dir)

    root = proj if proj else \
        Path(args.root).expanduser() if args.root else \
        Path(profile["root"]).expanduser() if profile.get("root") else Path.home()
    wanted = args.harness or profile.get("harnesses", list(ADAPTERS))
    unknown = [h for h in wanted if h not in ADAPTERS]
    if unknown:
        sys.exit(f"unknown harness(es): {', '.join(unknown)} (known: {', '.join(ADAPTERS)})")
    norm = skillmod.normalize(skills_cfg)
    # Skills are user-scope (symlinked into $HOME harness dirs) — not fetched per repo.
    skill_paths = {} if proj else \
        skillmod.resolve(norm, root / ".cache/agentsync/skills", do_fetch=(args.command == "apply"))
    ctx = Ctx(repo=REPO, root=root, config=config_dir, instructions=config_dir / "instructions.md",
              skills=skillmod.tiers(norm), servers=servers, profile=profile,
              verb=args.command, scope="project" if proj else "user",
              skill_paths=skill_paths, overrides=overrides)

    if args.command == "doctor":
        return doctor(ctx, wanted)
    if args.command == "docs":
        changed, _ = gen_docs.generate(ctx, write=True)
        print(f"docs: {'regenerated ' + ', '.join(changed) if changed else 'already up to date'} "
              f"({ctx.config / 'docs'})")
        return 0

    if not args.json:
        print(f"{args.command}: config={config_dir.name} root={root} harnesses={','.join(wanted)}\n")
    reports = [run_adapter(ADAPTERS[h], ctx, args.no_mcp_import) for h in wanted]
    drift = any(rep.drift for rep in reports)
    doc_drift = False
    if args.command == "verify" and ctx.scope == "user":  # inventory docs are user-scope
        _, doc_drift = gen_docs.generate(ctx, write=False)
        drift = drift or doc_drift

    # Machine-readable output for CI gating: same data, same exit codes, no prose.
    if args.json:
        print(json.dumps({
            "command": args.command, "config": str(config_dir), "root": str(root),
            "drift": drift, "docs_drift": doc_drift,
            "harnesses": [{"name": rep.name, "drift": rep.drift,
                           "lines": [{"status": s, "message": m} for s, m in rep.lines],
                           "diffs": rep.diffs} for rep in reports],
        }, indent=2))
        return 1 if args.command == "verify" and drift else 0

    for rep in reports:
        print(f"[{rep.name}]")
        for status, msg in rep.lines:
            print(f"  {ICON.get(status, '?')} {msg}")
    if args.command == "diff":
        blocks = [b for rep in reports for b in rep.diffs]
        if blocks:
            print("\n--- pending changes ---")
            print("".join(blocks))
    print()

    # Inventory docs: regenerate on apply, drift-check on verify (kept automatically fresh).
    if args.command == "apply" and ctx.scope == "user":
        changed, _ = gen_docs.generate(ctx, write=True)
        if changed:
            print(f"[docs] regenerated: {', '.join(changed)}")
    elif doc_drift:
        print("[docs] out of date — run `apply` (or `agentsync docs`)")

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
