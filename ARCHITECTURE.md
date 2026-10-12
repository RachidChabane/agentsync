# Architecture

The design rationale, grounded in established software-engineering practice. If
`README.md` is *what it does*, this is *why it's shaped this way*.

## What "great" means here

Not a vague aspiration — six concrete properties, each bought by one named practice:

| Property | Bought by | How it shows up |
|---|---|---|
| **Adoptable** out of the box | Convention over Configuration | `init.sh` detects harnesses, scaffolds `config/`, applies. Zero-config common case. |
| **Extensible** to new harnesses | Open/Closed + Adapter + Registry | A new harness is a new module + one registry line. No edits to existing code. |
| **Agnostic / portable** | Dependency Inversion + env-as-config | Policy depends on a neutral schema, not on any one LLM/tool. No hardcoded paths (`$HOME`, OS-aware dirs). |
| **Verifiable** | Declarative reconcile + drift check + tests | `apply` converges; `verify` reports drift; the suite runs in a sandbox. |
| **Lean / token-efficient** | DRY single-source + the determinism protocol | One definition → N renderings (no duplication). Scripts over re-derivation. |
| **Comprehensible** | Separation of mechanism from policy | `core/` (engine) vs `config/` (yours) is visible in the tree. |

## The spine: mechanism / policy separation

The one move that makes this open-sourceable. The engine (`core/`) holds *no* personal
data — no paths, no specific skills, no specific servers. Your choices live in `config/`
(git-ignored; `config.example/` is the tracked template). Anyone clones the engine and
brings their own policy. Everything else below is downstream of this cut.

## Patterns applied (and where they earn their place)

- **Adapter + Registry (Open/Closed).** Each harness implements a tiny interface
  (`capabilities()`, `apply(ctx)`). `ADAPTERS` is a plain dict. Eight real
  implementations justify the abstraction (the four file-based ones share a
  `FileHarness` base — paths + an MCP entry renderer); there is deliberately **no**
  plugin-discovery DSL or dynamic loader — that would be speculative for in-repo adapters.
- **Reconciliation loop (declarative IaC, à la Terraform/Ansible).** Each adapter
  describes *what it manages* as a list of `targets.py` objects (Link / Json / Merge /
  ClaudeMcp); the reconciler interprets that one description for **five verbs** — apply
  (converge), verify (drift), diff (preview), uninstall (surgical removal), doctor
  (inspect). Adding a verb touches the targets, not the four adapters.
  Every helper is idempotent, so re-running is a no-op and `verify` right after `apply`
  is clean. Drift for shared files (e.g. `settings.json`) is defined as *"would our
  managed keys change?"* — computed by running the same idempotent mutation on a copy —
  so a user's unrelated edits never read as drift. Convergence also runs the other
  way: each adapter records what it put in place (`managed.json`), and a later run
  releases whatever the config stopped declaring — exactly the recorded keys, hooks,
  links and files, never content agentsync did not write. Without that record a
  removed hook or key would live on in the shared file forever.
- **Dependency Inversion via a *thin* IR.** The canonical config is the abstraction both
  sides depend on. It's intentionally thin: only **MCP** and **enforcement wiring**
  genuinely diverge per harness and get adapter treatment. Instructions are plain
  markdown (one `@include` expansion, then a rendered file or an inline block) and
  skills are the open Agent Skills standard (linking + tiers) — wrapping those in a
  schema would be abstraction for its own sake.
- **Capability detection over version-sniffing.** `capabilities()` lets the reconciler
  degrade gracefully (VS Code: no MCP/skill surface) instead of failing. This is the
  honest path to "harness-agnostic."
- **Convention over Configuration.** Standard verb names; `init` infers the rest.
- **Facade.** `make` (or `python3 -m core.agentsync`) is the single front door.

## Instructions are composed, then always rendered

`config/instructions.md` can pull a self-contained block of rules in with one
`@include <path>` line, so a block that belongs to one context (an employer, a client,
a machine) lives in its own file and leaves every harness when that line goes.
`core/instructions.py` owns the whole syntax — pure text and paths, no harness
knowledge — and every adapter reads the expanded text through
`Adapter._instructions_text`, so no harness can see a raw directive. Expansion is one
level deep by design: an included file holds rules, not structure, which keeps cycles
impossible and every error a single `file:line`. The CLI expands every source before
any verb runs, so a bad directive fails before a single write.

A directory target is a **layer** — a directory shaped like `config/` — so the same
one-line switch carries a context's MCP servers, skills and settings along with its
text. `core/layers.py` merges a layer into the base config before any adapter runs
(named entries unique, overrides merged recursively, conflicts fatal), so adapters
never know a layer existed; removing the line is just a config change the reconciler
releases like any other. Layers attach to the shared `instructions.md` only, because
their JSON applies to every harness.

Rendering is unconditional. A symlink would hand a harness the raw directive, and
switching a path between "symlink" and "rendered file" as the config changes would make
the reconciler snapshot its own earlier rendering as the user's original. Every owned
file agentsync creates carries the same trap — without a record, its first rewrite would
back up agentsync's own output. The **originals ledger** closes it for every target:
the pre-agentsync state of a path is captured once, on first contact, and recorded
whether or not there was anything to keep; `uninstall` restores the `.bak` and forgets
the path.

## The determinism protocol as the reference plugin

The protocol isn't bolted on — it's the flagship demonstration of the extension model:
"an enforcement capability each adapter renders." It also proves the adapter interface is
real (each harness wires a session nudge + a commit gate its own way).

Key portability choice: the **verb set is the standard; the task runner is a binding.**
`_runner.sh` detects mise/make/just/npm behind one interface, so the protocol is neither
harness-locked nor runner-locked. The principle itself is the established norm
(Anthropic's *Building Effective Agents*: workflows over agents; 12-Factor Agents:
own your control flow; Agent Skills: prefer scripts for deterministic ops).

### The LLM-judgment layer is explicit, not blurred

The engine is deterministic; the few tasks that need judgment ship as Agent Skills
(`skills/`), each a deterministic scaffold + forced judgment steps: **add-harness**
(scaffold an adapter ⟶ map the harness's docs), **author-verify** (scan for checks ⟶
choose the read-only ones), **import-config** (synthesize a config ⟶ `diff-prove.sh`
confirms nothing's lost). This is the determinism principle applied reflexively:
deterministic where encodable, AI only where it isn't, and the boundary named.

### Inventory docs are generated, not maintained

`config/docs/{skills,mcps,hooks,agents}.md` are derived from the sources (frontmatter
`description:`, `mcp.json`, the wired hooks) by `gen_docs.py`, regenerated on every
`apply` and drift-checked on `verify`. This is the determinism principle applied to
documentation: a generated artifact + a drift gate beats a doc someone must remember to
update — exactly the "repeatable → deterministic" rule, dogfooded.

### Upstream specs are watched, not remembered

Adapters encode facts about other tools' file formats — facts that rot. `spec_watch.py`
snapshots each adapter's primary-source doc pages (`docs/spec-sources.json` →
`docs/spec-snapshots/`) and a weekly CI cron diffs them; a change opens an issue with
the text diff. Detection is deterministic and token-free; only the judgment step (does
this change affect an adapter?) involves a human or agent. Same split as everywhere else.

## Sibling concerns share plumbing, not an engine

`plugpack.py` (v0.3) is a second concern: it packages one canonical plugin bundle into
Claude Code's and GitHub Copilot's native plugin/marketplace formats. Same thesis as
config-sync — one source, N tool-native renderings — deliberately **not** the same
machinery, because the problem shape differs:

- Config-sync *reconciles live files it shares with the user* — Merge/`.bak`/surgical
  uninstall earn their keep — and never transforms content (a skill is a symlink, MCP a
  fixed render, instructions a lossless include expansion). Packaging is *lossy content transformation* into an output tree the
  packager owns wholesale: uninstall is deleting `dist/`, drift is `pack --check` (or
  `git diff --exit-code` where `dist/` is committed).
- **Shared:** the low-level plumbing (`util.dump`/`load_json`, `targets.udiff`),
  spec-watch (the plugin-format doc pages are just two more `spec-sources.json`
  entries), and the mechanism/policy principle. The rest of plugpack is net-new domain
  knowledge — the tool-name map, the warn-never-silent drop policy, the two MCP
  dialects. Forcing that through the reconciler would have bought only commodity
  plumbing at the price of a grand unified schema (deliberately deferred, below).
- **No Adapter ABC for two targets.** Per-tool knowledge lives in one module as a
  `TOOLMAP` dict + per-tool render branches; the `FileHarness` base earns itself at
  eight config harnesses, not two plugin targets. Extract a base when a genuinely
  divergent third target exists.

The seam for a third concern (another "one source → N tools" standard): a new
`core/<concern>.py` owning its verbs (`main(argv)`), one early-dispatch line in
`agentsync.main`, a test file in the Makefile gate, and its primary-source pages in
`spec-sources.json`. Nothing else changes — concerns are siblings behind one front
door, not plugins of a framework.

### Enforcement is layered, and honest about its limits

| Layer | Mechanism | Guarantees |
|---|---|---|
| Rule | `instructions.md`, synced everywhere | the agent is always *told* |
| Nudge | SessionStart / userPromptSubmitted hook | the agent always *sees* the repo's front door (or to scaffold) |
| Adoption | `scaffold-determinism` | any repo joins the standard in one command |
| Gate | PreToolUse commit hook → `verify`, exit 2 | no agent commit lands on a failing `verify` (fails open otherwise) |

What stays probabilistic, stated plainly: **the agent *choosing* to extract a
deterministic path in the first place.** No hook reads that intent; the rule + the gate
raise the odds and enforce once adopted, but they don't force the decision. The hooks
are themselves the protocol's "must-always-run → hook" category, dogfooded.

## Deliberately deferred (YAGNI with a trigger)

Applying SOLID *where four implementations prove it* and skipping it elsewhere is the
judgment, not cargo-culting every pattern. Not built until the trigger fires:

- **Plugin-discovery framework / dynamic adapter loading** — when an *external*
  (out-of-repo) adapter actually arrives.
- **A grand unified config schema** across all four concerns — only MCP + enforcement
  diverge enough to warrant structure; the rest are files.
- **Config schema-validation framework** — a small check is enough.
- **Global git `core.hooksPath` pre-commit** that also gates *human* commits — invasive
  (shadows repo-local hooks); out of scope for "make *agents* comply."

## Per-harness quirks handled (verified against the live tools)

- **Claude**: user-scope MCP lives in the stateful `~/.claude.json` and can't be
  symlinked → render an artifact + import via the `claude` CLI as an isolated side step
  (skipped in `--check` and any sandbox). `skillOverrides` is the only 4-tier model;
  others collapse to hidden/visible. Each adapter renders the tier it resolves for its
  own name (`Ctx.tiers_for`): a `tier` map's harness key, else its `"default"`.
- **Copilot CLI**: stdin is `toolArgs` (a JSON *string*), not `tool_input.command`; its
  `sessionStart` can't inject context, so the nudge runs on `userPromptSubmitted` once
  per session (sentinel). Fail-closed harness — the gate only ever exits 0/2.
- **VS Code Copilot**: no external user-scope instruction file → inline into settings.
  Reads hooks from *files* (not its settings' hooks key), so it gets its own dedicated
  agentsync hooks file (gate + nudge + the user's VS-Code hooks) via
  `chat.hookFilesLocations` — self-contained, not borrowing Claude's file. Requires the
  `additionalContext` JSON envelope; ignores `matcher`, so the guard self-filters.
- **OpenCode**: no shell-hook surface → a JS plugin (`tool.execute.before` throws to
  block); no clean session-start injection → push to the system prompt via an
  `experimental.*` hook that degrades safely if it changes.
