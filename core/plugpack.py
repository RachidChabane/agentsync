"""plugpack — package ONE canonical plugin bundle into each AI tool's native plugin
and marketplace format (Claude Code; GitHub Copilot CLI + VS Code).

Sibling concern to config-sync: same thesis (one source -> N tool-native renderings),
deliberately NOT the same engine. Config-sync symlinks/merges *live user files* and
never transforms content; packaging is *lossy content transformation* into an output
tree this module owns wholesale (uninstall = delete the out dir; drift = `--check`,
or `git diff --exit-code` when the output is committed). Only low-level plumbing is
shared (targets.udiff, util.dump/load_json).

  python3 -m core.plugpack SRC [--out DIR] [--tool claude|copilot] [--check] [--strict]
  agentsync pack SRC ...                       # same thing, via the front door

Canonical bundle layout (SRC):
  bundle.json          {"name", "description", "version", "owner": {"name", ...}} —
                       optional; name falls back to the bundle directory's name
  skills/<name>/...    Agent Skills (open standard) — copied verbatim, never transformed
  agents/<name>.md     agent definitions: markdown body + neutral frontmatter (below)
  commands/<name>.md   slash commands, Claude dialect (description/argument-hint/
                       $ARGUMENTS) — DECLINED with a warning for Copilot: no verified
                       command-file format exists on that surface
  mcp.json             MCP servers in the Claude-plugin dialect (BARE server-name keys,
                       verified against anthropics/claude-plugins-official); the Copilot
                       output wraps the same entries in {"mcpServers": ...}

Agent frontmatter — the neutral vocabulary (authors write tool grants ONCE):
  name           optional; synthesized from the filename when absent (Claude requires
                 a kebab-case name; Copilot falls back to the filename anyway)
  description    required
  tools          list mixing neutral ids (TOOLMAP keys), MCP globs ("server/*" or
                 "server/tool"), and single-tool escapes ("claude:LSP",
                 "copilot:read/problems") that render for that one tool only
  model          Claude model alias — dropped WITH A WARNING for Copilot
  argument-hint  VS Code surface — dropped WITH A WARNING for Claude
  handoffs       list of {label, agent, prompt, send} — Copilot only, warned for Claude

Every lossy decision warns on stderr; nothing degrades silently (--strict turns
warnings into exit 2 for CI). Formats verified 2026-07 against primary sources —
the same pages are snapshot in docs/spec-sources.json, so spec-watch flags upstream
format drift weekly. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .targets import udiff
from .util import dump, load_json

TOOLS = ("claude", "copilot")

# Neutral tool vocabulary -> per-tool grant ids. Claude ids: code.claude.com/docs/en/
# sub-agents + tools-reference (comma-separated string in frontmatter). Copilot ids:
# the VS Code built-in tools table (namespaced generation) + bare group grants as used
# by live awesome-copilot agents ('read', 'search', 'web', 'edit').
TOOLMAP = {
    "read": {"claude": ["Read"], "copilot": ["read"]},
    "edit": {"claude": ["Edit", "Write", "NotebookEdit"], "copilot": ["edit"]},
    "search": {"claude": ["Grep", "Glob"], "copilot": ["search"]},
    "execute": {"claude": ["Bash"], "copilot": ["execute/runInTerminal"]},
    "web": {"claude": ["WebFetch", "WebSearch"], "copilot": ["web"]},
    "subagents": {"claude": ["Agent"], "copilot": ["agent/runSubagent"]},
    "todos": {"claude": ["TaskCreate", "TaskGet", "TaskList", "TaskUpdate"],
              "copilot": ["todos"]},
}
AGENT_KEYS = {"name", "description", "tools", "model", "argument-hint", "handoffs"}
META_KEYS = ("description", "version", "author", "homepage", "repository", "license",
             "keywords")


def _scalar(v: str):
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_scalar(x.strip()) for x in inner.split(",")] if inner else []
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    if v in ("true", "false"):
        return v == "true"
    return v


def parse_front(text: str):
    """Tiny YAML-subset parser for the canonical frontmatter: scalars, inline lists,
    and block lists of scalars or flat dicts (handoffs). Not general YAML — the
    canonical schema is deliberately small enough not to need it."""
    m = re.match(r"---\n(.*?)\n---[ \t]*\n?(.*)", text, re.S)
    if not m:
        return {}, text
    fields, key = {}, None
    for ln in m.group(1).splitlines():
        if not ln.strip():
            continue
        if not ln[0] in " \t-" and ":" in ln:
            key, _, val = ln.partition(":")
            key, val = key.strip(), val.strip()
            fields[key] = _scalar(val) if val else []
        elif ln.lstrip().startswith("- ") and key is not None:
            item = ln.lstrip()[2:].strip()
            if ":" in item:                      # first line of a dict item
                k, _, v = item.partition(":")
                fields[key].append({k.strip(): _scalar(v.strip())})
            else:
                fields[key].append(_scalar(item))
        elif key is not None and fields.get(key) and isinstance(fields[key], list) \
                and isinstance(fields[key][-1], dict) and ":" in ln:
            k, _, v = ln.strip().partition(":")  # continuation of a dict item
            fields[key][-1][k.strip()] = _scalar(v.strip())
    return fields, m.group(2)


def _q(v) -> str:
    """Quote a YAML scalar only when a plain one would be ambiguous."""
    if isinstance(v, bool):
        return "true" if v else "false"
    v = str(v)
    if re.search(r"[:#'\"\[\]{}]|^[\s&*?|>%@`!-]|\s$", v) or not v:
        return "'" + v.replace("'", "''") + "'"
    return v


def _kebab(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def map_tools(tools, plugin: str, mcp: dict, agent: str, warns: list):
    """The lossy core: one neutral grant list -> a per-tool list for each target,
    warning on anything that cannot be expressed."""
    if isinstance(tools, str):                   # tolerate the Claude comma form
        tools = [t.strip() for t in tools.split(",") if t.strip()]
    out = {"claude": [], "copilot": []}
    for t in tools:
        if not isinstance(t, str):
            warns.append(f"agent {agent}: malformed tools entry {t!r} dropped")
            continue
        if t.startswith("claude:"):
            out["claude"].append(t[7:])
        elif t.startswith("copilot:"):
            out["copilot"].append(t[8:])
        elif "/" in t:                           # MCP glob: server/* or server/tool
            server, _, tool = t.partition("/")
            # servers shipped in this bundle get Claude's plugin-qualified MCP name
            base = f"mcp__plugin_{plugin}_{server}" if server in mcp else f"mcp__{server}"
            out["claude"].append(base if tool == "*" else f"{base}__{tool}")
            out["copilot"].append(t)
        elif t in TOOLMAP:
            for tool in TOOLS:
                out[tool] += TOOLMAP[t][tool]
        else:
            warns.append(f"agent {agent}: unknown tool '{t}' dropped for every target — "
                         f"not in the neutral vocabulary ({', '.join(TOOLMAP)}); use "
                         "'claude:<Tool>' or 'copilot:<id>' to target one tool explicitly")
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


def render_agent(path: Path, plugin: str, mcp: dict, warns: list):
    """One canonical agent -> (claude_name, claude_md, copilot_md)."""
    fields, body = parse_front(path.read_text())
    aname = str(fields.get("name") or path.stem)
    if not fields.get("description"):
        sys.exit(f"error: {path}: agent frontmatter needs a description")
    for k in sorted(set(fields) - AGENT_KEYS):
        warns.append(f"agent {aname}: frontmatter key '{k}' is not in the canonical "
                     "schema — dropped")
    grants = map_tools(fields.get("tools", []), plugin, mcp, aname, warns)

    cl = [f"name: {_q(_kebab(aname))}", f"description: {_q(fields['description'])}"]
    if grants["claude"]:
        cl.append("tools: " + ", ".join(grants["claude"]))  # Claude: comma STRING
    if fields.get("model"):
        cl.append(f"model: {_q(fields['model'])}")
    for k in ("argument-hint", "handoffs"):
        if fields.get(k):
            warns.append(f"agent {aname}: '{k}' has no Claude surface — dropped for claude")

    co = [f"name: {_q(aname)}", f"description: {_q(fields['description'])}"]
    if grants["copilot"]:
        co.append("tools: [" + ", ".join(f"'{t}'" for t in grants["copilot"]) + "]")
    if fields.get("argument-hint"):
        co.append(f"argument-hint: {_q(fields['argument-hint'])}")
    if fields.get("handoffs"):
        co.append("handoffs:")
        for h in fields["handoffs"]:
            first = True
            for k, v in h.items():
                co.append(f"  {'- ' if first else '  '}{k}: {_q(v)}")
                first = False
    if fields.get("model"):
        warns.append(f"agent {aname}: model '{fields['model']}' is a Claude alias — "
                     "dropped for copilot (no portable model vocabulary)")

    def doc(head):
        return "---\n" + "\n".join(head) + "\n---\n" + body.rstrip("\n") + "\n"
    return _kebab(aname), doc(cl), doc(co)


def render(src: Path):
    """Canonical bundle -> {out-relative path: bytes} for both tools, plus warnings.
    Each tool's subtree is a real MARKETPLACE root holding one plugin, so the output
    is directly installable (claude plugin marketplace add <out>/claude)."""
    if not src.is_dir():
        sys.exit(f"error: {src} is not a directory")
    meta = load_json(src / "bundle.json") or {}
    name = str(meta.get("name") or _kebab(src.resolve().name))
    if name != _kebab(name):
        sys.exit(f"error: bundle name '{name}' must be kebab-case (both ecosystems require it)")
    mcp = load_json(src / "mcp.json") or {}
    if "mcpServers" in mcp:
        sys.exit(f"error: {src / 'mcp.json'} must use bare server-name keys (the Claude-"
                 "plugin dialect) — the copilot output adds the mcpServers wrapper itself")
    warns: list = []
    files: dict = {}
    root = {"claude": f"claude/plugins/{name}", "copilot": f"copilot/plugins/{name}"}

    # skills + any other bundle docs: verbatim pass-through (the portable part)
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src).as_posix()
        if p.is_file() and rel.split("/")[0] == "skills":
            for t in TOOLS:
                files[f"{root[t]}/{rel}"] = p.read_bytes()

    seen: dict = {}
    for p in sorted(src.glob("agents/*.md")):
        cname, cmd, comd = render_agent(p, name, mcp, warns)
        if cname in seen:
            sys.exit(f"error: agents {seen[cname]} and {p.name} both map to claude "
                     f"name '{cname}' — rename one")
        seen[cname] = p.name
        files[f"{root['claude']}/agents/{cname}.md"] = cmd.encode()
        files[f"{root['copilot']}/agents/{p.stem}.agent.md"] = comd.encode()

    for p in sorted(src.glob("commands/*.md")):
        files[f"{root['claude']}/commands/{p.name}"] = p.read_bytes()
        warns.append(f"command {p.stem}: not rendered for copilot — no verified command-"
                     "file format on that surface; express it as a skill for portability")

    if mcp:
        files[f"{root['claude']}/.mcp.json"] = dump(mcp).encode()
        files[f"{root['copilot']}/.mcp.json"] = dump({"mcpServers": mcp}).encode()

    owner = meta.get("owner") or meta.get("author") or {"name": name}
    manifest = {"name": name, **{k: meta[k] for k in META_KEYS if k in meta}}
    manifest.setdefault("author", owner)  # claude validate warns without attribution
    files[f"{root['claude']}/.claude-plugin/plugin.json"] = dump(manifest).encode()
    co_manifest = dict(manifest)
    pre = f"{root['claude']}/skills/"
    skill_dirs = sorted({f[len(pre):].split("/")[0] for f in files if f.startswith(pre)})
    if skill_dirs:
        co_manifest["skills"] = [f"./skills/{d}/" for d in skill_dirs]
    if mcp:
        co_manifest["mcpServers"] = ".mcp.json"
    # agents: deliberately omitted — the generic Copilot CLI spec scans agents/ by
    # default and its explicit form takes directories, while awesome-copilot's linter
    # wants per-file paths; the default scan is the only shape valid for both.
    files[f"{root['copilot']}/.github/plugin/plugin.json"] = dump(co_manifest).encode()

    entry = {"name": name,
             **{k: meta[k] for k in ("description", "version") if k in meta}}
    files["claude/.claude-plugin/marketplace.json"] = dump({
        "name": f"{name}-marketplace",
        **({"description": meta["description"]} if "description" in meta else {}),
        "owner": owner,
        "plugins": [{**entry, "source": f"./plugins/{name}"}]}).encode()
    market: dict = {"name": f"{name}-marketplace"}
    md = {k: meta[k] for k in ("description", "version") if k in meta}
    if md:
        market["metadata"] = md
    market.update(owner=owner, plugins=[{**entry, "source": f"plugins/{name}"}])
    files["copilot/.github/plugin/marketplace.json"] = dump(market).encode()
    return files, warns


def pack(files: dict, out: Path, tools) -> None:
    """Converge the owned output tree: write what changed, prune what we no longer
    render (the packager owns these subtrees wholesale)."""
    for rel, data in sorted(files.items()):
        p = out / rel
        if not (p.exists() and p.read_bytes() == data):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            print(f"write: {rel}")
    for t in tools:
        troot = out / t
        if not troot.exists():
            continue
        for p in sorted(troot.rglob("*"), reverse=True):
            if p.is_file() and p.relative_to(out).as_posix() not in files:
                p.unlink()
                print(f"prune: {p.relative_to(out).as_posix()}")
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()


def check(files: dict, out: Path, tools) -> int:
    """Read-only drift check against the packed output; exit-1 semantics like verify."""
    drift = []
    for rel, data in sorted(files.items()):
        p = out / rel
        if not p.exists():
            drift.append((f"missing: {rel}", ""))
        elif p.read_bytes() != data:
            drift.append((f"differs: {rel}",
                          udiff(rel, p.read_bytes().decode(errors="replace"),
                                data.decode(errors="replace"))))
    for t in tools:
        troot = out / t
        for p in sorted(troot.rglob("*")) if troot.exists() else []:
            if p.is_file() and p.relative_to(out).as_posix() not in files:
                drift.append((f"unexpected: {p.relative_to(out).as_posix()}", ""))
    for msg, diff in drift:
        print(f"DRIFT {msg}")
        if diff:
            print(diff, end="")
    print("drift — re-run `agentsync pack` (or fix the bundle)." if drift
          else "ok: packed output matches the bundle.")
    return 1 if drift else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="agentsync pack",
        description="package a canonical plugin bundle into Claude Code + Copilot "
                    "native plugin/marketplace trees")
    ap.add_argument("src", help="bundle directory (see core/plugpack.py docstring)")
    ap.add_argument("--out", help="output directory (default: SRC/dist)")
    ap.add_argument("--tool", choices=TOOLS, help="limit to one target tool")
    ap.add_argument("--check", action="store_true",
                    help="read-only drift check against --out; exit 1 on drift")
    ap.add_argument("--strict", action="store_true", help="exit 2 if anything warned")
    args = ap.parse_args(argv)
    src = Path(args.src).expanduser()
    out = Path(args.out).expanduser() if args.out else src / "dist"
    tools = [args.tool] if args.tool else list(TOOLS)
    files, warns = render(src)
    files = {r: d for r, d in files.items() if r.split("/", 1)[0] in tools}
    for w in sorted(set(warns)):
        print(f"warn: {w}", file=sys.stderr)
    if args.check:
        rc = check(files, out, tools)
    else:
        pack(files, out, tools)
        print(f"packed: {src.name} -> {out} ({len(files)} files, "
              f"{len(warns)} warning{'s' if len(warns) != 1 else ''})")
        rc = 0
    return 2 if args.strict and warns else rc


if __name__ == "__main__":
    sys.exit(main())
