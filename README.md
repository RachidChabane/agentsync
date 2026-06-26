# agentsync

**One declarative config, rendered into every AI coding assistant — plus a
determinism-over-AI protocol that makes itself stick in every repo.**

You configure your AI coding setup *once* — instructions, MCP servers, skill
availability, enforcement — and `agentsync` renders it into each tool's native files
(Claude Code, GitHub Copilot CLI, OpenCode, VS Code Copilot). It's LLM-agnostic,
harness-agnostic, and token-efficient by design.

```bash
git clone <repo> && cd agentsync
./init.sh          # detects your harnesses, creates config/, installs the scaffolder
#                    edit config/{instructions.md, mcp.json, skills.json} ...
make apply         # ... then render it into every tool
```

First run stops after creating `config/` (so placeholders never reach your live tools).
After that, edit `config/` and re-run `make apply` to update — idempotent.

## Commands

`init.sh` puts an `agentsync` CLI on your PATH; run it from anywhere (it operates on the
repo's `config/`):

| Command | What it does |
|---|---|
| `agentsync apply` | render config into every enabled harness (idempotent) |
| `agentsync verify` | read-only drift check; exit 1 if any harness diverged |
| `agentsync diff` | **preview the exact change** (unified diff) before touching anything |
| `agentsync uninstall` | remove only what agentsync added; restore `.bak` originals |
| `agentsync doctor` | health check: harnesses, runners, PATH, MCP auth, drift, broken links |

`--root DIR` targets a sandbox instead of `$HOME`; `--harness NAME` limits scope.

## What agentsync owns vs preserves

agentsync edits *shared* config files (your `settings.json`) by **merge**: it owns a few
specific keys and leaves everything else alone. So `agentsync diff` before `apply` shows
exactly what moves, and anything not listed below is yours to hand-edit freely.

| Harness | Owned (set from `config/`, hand-edits overwritten) | Preserved |
|---|---|---|
| Claude | `skillOverrides`; the SessionStart + PreToolUse[Bash] determinism hooks; `mcp-servers.json` + user-scope MCP | every other settings key/hook |
| Copilot | `disabledSkills`; the userPromptSubmitted + preToolUse hooks; `mcp-config.json` | everything else |
| OpenCode | `opencode.json` keys `mcp`, `permission.skill`, `instructions` | every other key |
| VS Code | the instructions block, `chat.useCustomAgentHooks`, one `chat.hookFilesLocations` entry | everything else |

Owned hooks are keyed by script name, so a stale entry left after the repo moves is
replaced (not duplicated) and shows up in `verify`. Want to change an owned value? Edit
`config/`, not the tool's file.

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
├── instructions.md            ├── agentsync.py    reconciler: apply/verify/diff/…
├── skills.json   (tiers       ├── targets.py      declarative target model
│                  + sources)  ├── adapters/       one per harness (the only
├── mcp.json      (servers)    │   ├── claude.py    per-harness knowledge)
├── profile.json  (enabled)    │   ├── copilot.py
└── overrides.json (passthru)  │   ├── opencode.py / vscode.py
                               ├── skills.py       skill source resolution (local/git)
                               └── util.py         context, report, fs primitives
```

You bring `config/`; the engine renders it. Each **adapter** translates the shared
config into one harness's dialect. Adding a new harness = one new adapter module + one
registry line — nothing else changes.

Two `config/` knobs make agentsync able to own your *whole* setup, not just four
concerns:
- **Skill sourcing** — a skill entry can carry a `source` (local dir or git URL) and
  agentsync symlinks it into Claude's & Copilot's skills dirs (cloning/pulling git
  sources on apply), so skills are managed declaratively, not by hand.
- **Settings passthrough** (`overrides.json`) — own arbitrary per-harness settings keys
  (plugins, status line, model effort) and add your own hooks alongside the determinism
  ones. This is what lets agentsync replace a hand-maintained config wholesale.

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

## Skills — the LLM-judgment layer

The engine is deterministic; tasks that genuinely need judgment ship as Agent Skills in
`skills/`, each pairing a deterministic scaffold with forced judgment steps:

- **add-harness** — support a new harness. A script scaffolds + registers the adapter
  (deterministic); you read the harness's docs and fill its config/hook mapping (judgment).
- **author-verify** — fill a repo's `verify` verb. A script scans for fast checks
  (deterministic); you pick the read-only ones (judgment).
- **import-config** — migrate a hand-built config into `config/`. You synthesize it
  (judgment); `diff-prove.sh` proves nothing's lost (deterministic) before you switch.

That's the determinism principle applied to agentsync itself: deterministic where
encodable, AI only where it isn't — and the boundary is explicit, not blurred.

## Verify / test

```bash
make verify     # syntax-checks every source + runs the suite, writes nothing to $HOME
```

Tests run the reconciler into a temp dir (never your real config) and exercise the
commit gate in a throwaway git repo. See `ARCHITECTURE.md` for the design rationale.
