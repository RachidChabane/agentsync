# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **`@include` in instructions** (`core/instructions.py`): a line holding exactly
  `@include <path>` in `instructions.md` or an `instructions.<harness>.md` variant is
  replaced by that file's text in every harness, user and project scope. Paths are
  relative to the including file and must stay inside the config dir; directives in
  fenced code are plain text; a missing target, a nested directive, or a cyclic one
  aborts every verb with `file:line` before anything is written. Deleting the one
  directive line and re-applying removes the included block from every harness.
- **Config layers**: an `@include` whose target is a directory pulls in a whole layer
  shaped like the config dir — its `instructions.md` spliced at the line, its
  `mcp.json` / `skills.json` / `overrides.json` merged into the config
  (`core/layers.py`). Named servers and skills must be unique; overrides merge
  recursively (lists concatenate, scalars must agree); a conflict names the layer file
  and key path and aborts before any write. Deleting the one line and re-applying
  removes the layer's text, settings, hooks, MCP servers and skill links everywhere.
- **Services** (`core/services.py`): a `services.json` in the config dir or a layer
  declares a background job as an `install` and an `uninstall` command. `apply` installs
  it once and again only when the commands change, runs the recorded `uninstall` when
  the declaration disappears (a deleted layer `@include` line included), and keeps the
  record of a failing command so the next run retries; `agentsync uninstall` releases
  every recorded service. `verify` and `diff` execute nothing and report drift. Commands
  run only against the real `$HOME`; sandbox roots and project scope never run or
  record one.
- **Originals ledger** (`~/.config/agentsync/originals.json`; project scope:
  `.agentsync/originals.json`): the pre-agentsync state of each managed path is
  captured once, on first contact — a `.bak` when a real file was there, nothing when
  it was absent or a symlink.

- **Release of what the config drops**: each adapter records what it put in place
  (`~/.config/agentsync/managed.json`; project scope: `.agentsync/managed.json`). A
  settings key, passthrough hook, gate hook, skill link or owned file that the config
  no longer declares is removed on the next `apply` — only what the record says
  agentsync wrote, never a foreign hook or a user's own link — and `verify` reports it
  as drift until then. A path another enabled adapter still declares is kept.

### Changed
- **Instruction files are always rendered, never symlinked.** Claude, Copilot, Windsurf,
  Zed and Cline each get an owned file; OpenCode's `instructions` ref points at a
  rendered `~/.config/agentsync/opencode-instructions.md` (project scope:
  `.opencode/agentsync-instructions.md`) instead of the source. An edit to
  `config/instructions.md` now reaches the harnesses on the next `apply`, and
  `verify` reports a stale copy as drift. An existing symlink is replaced in place,
  without a `.bak`.

### Fixed
- A file agentsync had created itself was snapshotted as a `.bak` "original" the first
  time its content changed, so `uninstall` restored stale rendered content.

## [0.3.0]

### Added
- **`agentsync pack`** (`core/plugpack.py`): package one canonical plugin bundle
  (skills verbatim, agents with tool grants written once in a neutral vocabulary,
  commands, MCP) into Claude Code's and GitHub Copilot's native plugin + marketplace
  trees — each directly installable. Lossy translations always warn (`--strict` makes
  warnings fatal); `--check` is a read-only CI drift gate over the packed output.
  Both dialects verified against primary sources (bare-key vs `mcpServers`-wrapped
  `.mcp.json`, comma-string vs YAML-array tool grants, `.claude-plugin/` vs
  `.github/plugin/`) and proven end-to-end in both real CLIs; the source pages joined
  the spec-watch and the example bundle lives in `examples/demo-bundle/`.
- Golden-snapshot test (`tests/test_golden.py`): the rendered output of a full apply
  (8 harnesses, user + project scope) is locked byte-for-byte against a committed
  golden, so refactors provably cannot change config-sync's observable output.
- `spec_watch.py` + weekly CI cron: deterministic drift detection for the upstream
  harness docs each adapter's format facts came from; changes open an issue with the
  text diff.
- PyPI publishing workflow (OIDC trusted publishing) on every GitHub release.

### Fixed
- `docs/ci.md` drift action: explicit `shell: bash` (pipefail) so `tee` can't swallow
  verify's exit 1.

## [0.2.0]

### Added
- `verify --json` / `diff --json` — machine-readable reports (same exit codes) for CI
  drift gating, plus a copy-paste GitHub Action in `docs/ci.md`.
- `"enforcement"` key in `profile.json` (default `true`): set `false` to disable the
  determinism commit gate / session nudge / OpenCode plugin in every harness —
  config-sync only.
- `pyproject.toml` with a `console_scripts` entry point: `pipx install` / `uvx` work
  without cloning; an installed CLI reads its config from `~/.config/agentsync`.
- README positioning section (vs. rulesync / mcpm) and the AGENTS.md / SKILL.md interop
  note.
- Four new harnesses on a generic `FileHarness` base: **Cursor** (MCP; global rules are
  settings-UI-only), **Windsurf** (rules + MCP), **Zed** (AGENTS.md; MCP is JSONC —
  unmanaged), **Cline** (rules + MCP). Aider documented as not adaptable (no native MCP,
  YAML-only config).
- **Project scope**: `apply/verify/diff/uninstall --project [DIR]` renders committed,
  team-shared files (CLAUDE.md + .mcp.json, .github/copilot-instructions.md,
  opencode.json, .vscode/mcp.json, AGENTS.md, .cursor/mcp.json) from the repo's own
  `.agentsync/` config, with env-based auth headers.
- Per-harness instruction variants: `config/instructions.<harness>.md` appends to the
  shared instructions for that harness only.

### Fixed
- `verify`/`apply` crashed scanning agent dirs when `overrides.json` carried a top-level
  `_comment` string (as `config.example` ships).

## [0.1.0]

Initial public release.

### Added
- Declarative config (`instructions`, `mcp`, `skills`, `overrides`) rendered into Claude
  Code, GitHub Copilot CLI, OpenCode, and VS Code Copilot via per-harness adapters.
- Reconciler verbs: `apply`, `verify` (drift), `diff` (preview), `uninstall` (surgical),
  `doctor` (health), `docs` (regenerate inventory). Declarative target model behind them.
- Determinism protocol: runner-agnostic (`make`/`mise`/`just`/npm) commit gate +
  session nudge, wired per harness; `scaffold-determinism` one-command adoption.
- Skill sourcing (local dir or git) and arbitrary per-harness settings passthrough.
- Auto-generated, drift-checked inventory docs (`config/docs/`).
- Judgment-layer Agent Skills: `add-harness`, `author-verify`, `import-config`.
- `init.sh` zero-config setup; `agentsync` + `scaffold-determinism` CLIs on PATH.
- Dependency-free test suite + `make verify` front door; CI on every PR.
