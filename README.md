# agentsync

**One declarative config, rendered into every AI coding assistant — plus a
determinism-over-AI protocol that makes itself stick in every repo.**

You configure your AI coding setup *once* — instructions, MCP servers, skill
availability, enforcement — and `agentsync` renders it into each tool's native files
(Claude Code, GitHub Copilot CLI, OpenCode, VS Code Copilot). It's LLM-agnostic,
harness-agnostic, and token-efficient by design.

```bash
git clone <repo> && cd agentsync
./init.sh          # detects your installed harnesses, applies, installs the scaffolder
```

That's it. Edit `config/`, re-run `./init.sh` (or `make apply`) to update.

---

## Why

Every AI coding tool wants the same things configured — system instructions, which MCP
servers to load, which skills to expose, guardrails — but each in its own file format
and location. Keep them by hand and they drift. `agentsync` makes one source of truth
and a deterministic renderer, so:

- change a rule once → every tool gets it;
- a read-only `verify` proves no tool has drifted;
- the same config reproduces on a fresh machine in one command.

It ships with a second, opt-in idea baked in as the reference feature: the
**determinism protocol** — *if a repeatable task can be made deterministic, it should
be; use AI only for work that needs judgment that can't be encoded.* See below.

---

## Two pillars

### 1. Config sync (the engine)

```
config/ (yours)                core/ (the engine, harness-agnostic)
├── instructions.md            ├── agentsync.py        reconciler: apply / verify
├── skills.json   (tiers)      ├── adapters/           one per harness (the only
├── mcp.json      (servers)    │   ├── claude.py        per-harness knowledge)
└── profile.json  (enabled)    │   ├── copilot.py
                               │   ├── opencode.py
                               │   └── vscode.py
                               └── util.py             idempotent fs convergence
```

You bring `config/`; the engine renders it. Each **adapter** translates the shared
config into one harness's dialect. Adding a new harness = one new adapter module + one
registry line — nothing else changes.

| Concern | Claude Code | Copilot CLI | OpenCode | VS Code Copilot |
|---|---|---|---|---|
| Instructions | `~/.claude/CLAUDE.md` | `~/.copilot/copilot-instructions.md` | `opencode.json` ref | inlined in settings |
| MCP servers | artifact + CLI import | `mcp-config.json` | `opencode.json` `mcp` | — (no surface) |
| Skill tiers | `skillOverrides` (4-way) | `disabledSkills` | `permission.skill` | — |
| Enforcement | hooks | hooks | JS plugin | reuses Claude's hooks |

Dashes are honest **graceful degradation**: VS Code exposes no MCP/skill surface, so the
adapter declares it doesn't manage those (`capabilities()`) instead of faking it.

### 2. The determinism protocol (the reference feature)

A portable convention + enforcement so repeatable work becomes scripts, not repeated AI
calls (cheaper, predictable, testable):

- **Convention** — the standard verb set `setup` / `verify` / `test` / `run`
  ([Scripts to Rule Them All](https://github.com/github/scripts-to-rule-them-all)),
  exposed through whatever **task runner** the repo uses — `make`, `mise`, `just`, or
  npm. The verbs are the standard; the runner is just a binding.
- **Adoption** — `scaffold-determinism` drops a front door (default: a `Makefile`) with
  the standard verbs into any repo, in one command.
- **Enforcement** (wired by `agentsync apply`, per harness):
  - a **session nudge** surfaces the repo's tasks (or tells the agent to scaffold);
  - a **commit gate** runs the repo's fast `verify` before any agent `git commit` and
    blocks on failure. It **fails open** — no runner, no `verify` verb, or a timeout all
    let the commit through, so it can never wedge a repo.

`verify` is the fast, read-only, commit-safe verb; slow suites go under `test`.

---

## Requirements

- **bash**, **python3** (stdlib only — no pip installs), **git**.
- For the determinism front door: any one of **make** / **mise** / **just** / **npm**
  (make is preinstalled almost everywhere; the scaffolder defaults to it).
- Node is only needed if you use the OpenCode plugin.

## Extending

- **New harness** → add `core/adapters/<name>.py` (subclass `Adapter`, implement
  `capabilities()` + `apply()`), then add it to `ADAPTERS` in `core/adapters/__init__.py`.
  The reconciler is closed for modification (Open/Closed).
- **New task runner** → extend the four `case` blocks in `core/enforcement/_runner.sh`
  (and the `detect()` table in `opencode-plugin.js`).

## Verify / test

```bash
make verify     # syntax-checks every source + runs the suite, writes nothing to $HOME
```

Tests run the reconciler into a temp dir (never your real config) and exercise the
commit gate in a throwaway git repo. See `ARCHITECTURE.md` for the design rationale.
