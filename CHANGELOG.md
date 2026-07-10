# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

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
