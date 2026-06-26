#!/usr/bin/env python3
"""agentsync reconciler — one declarative config, rendered into every AI coding harness.

  python3 -m core.agentsync apply   [--root DIR] [--config DIR] [--harness N ...]
  python3 -m core.agentsync verify  [...]   # read-only drift check, exit 1 on drift

Mechanism only: loads the config, then asks each enabled adapter to converge (apply) or
report drift (verify). Adapters hold all per-harness knowledge. Idempotent; safe to
re-run. The one stateful side effect — importing Claude's MCP via its CLI — is isolated
here and only runs on a real apply into the real $HOME (never in --check or a sandbox).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from core.adapters import ADAPTERS
from core.util import Ctx, Report

REPO = Path(__file__).resolve().parents[1]
ICON = {"ok": "·", "write": "✎", "link": "→", "skip": "–", "drift": "✗"}


def load_config(config_dir: Path):
    def jload(name):
        p = config_dir / name
        return json.loads(p.read_text()) if p.exists() else {}
    profile = jload("profile.json")
    skills = jload("skills.json").get("skills", {})
    servers = jload("mcp.json").get("servers", {})
    return profile, skills, servers


def claude_mcp_import(ctx: Ctx) -> Report:
    """Import the rendered Claude MCP artifact via the `claude` CLI (the one config that
    can't be symlinked). Best-effort; skipped unless writing into the real $HOME."""
    rep = Report("claude-mcp")
    artifact = ctx.root / ".claude" / "mcp-servers.json"
    if ctx.check or ctx.root != Path.home():
        rep.skipped("mcp import: sandbox/check — artifact written, CLI import skipped")
        return rep
    import shutil
    if not shutil.which("claude"):
        rep.skipped("mcp import: `claude` CLI not found — run `claude mcp add-json` yourself")
        return rep
    servers = json.loads(artifact.read_text())
    for name, spec in servers.items():
        subprocess.run(["claude", "mcp", "remove", name, "-s", "user"],
                       capture_output=True)
        r = subprocess.run(["claude", "mcp", "add-json", name, json.dumps(spec), "-s", "user"],
                           capture_output=True)
        (rep.wrote if r.returncode == 0 else rep.skipped)(f"mcp import: {name}")
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agentsync")
    ap.add_argument("command", choices=["apply", "verify"])
    ap.add_argument("--root", help="target root to write into (default: $HOME)")
    ap.add_argument("--config", help="config dir (default: ./config, else ./config.example)")
    ap.add_argument("--harness", action="append", help="limit to these harnesses (repeatable)")
    ap.add_argument("--no-mcp-import", action="store_true", help="skip the Claude MCP CLI import")
    args = ap.parse_args(argv)

    config_dir = Path(args.config) if args.config else (
        REPO / "config" if (REPO / "config").exists() else REPO / "config.example")
    profile, skills, servers = load_config(config_dir)

    root = Path(args.root).expanduser() if args.root else \
        Path(profile["root"]).expanduser() if profile.get("root") else Path.home()
    wanted = args.harness or profile.get("harnesses", list(ADAPTERS))
    unknown = [h for h in wanted if h not in ADAPTERS]
    if unknown:
        print(f"unknown harness(es): {', '.join(unknown)} (known: {', '.join(ADAPTERS)})",
              file=sys.stderr)
        return 2

    ctx = Ctx(repo=REPO, root=root, instructions=config_dir / "instructions.md",
              skills=skills, servers=servers, profile=profile, check=(args.command == "verify"))

    print(f"{args.command}: config={config_dir.name} root={root} "
          f"harnesses={','.join(wanted)}\n")
    reports = [ADAPTERS[h].apply(ctx) for h in wanted]
    if args.command == "apply" and "claude" in wanted and not args.no_mcp_import:
        reports.append(claude_mcp_import(ctx))

    drift = False
    for rep in reports:
        print(f"[{rep.name}]")
        for status, msg in rep.lines:
            print(f"  {ICON.get(status, '?')} {msg}")
        drift = drift or rep.drift
    print()
    if ctx.check:
        print("DRIFT — run `apply` to converge." if drift else "ok: all harnesses match config.")
        return 1 if drift else 0
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
