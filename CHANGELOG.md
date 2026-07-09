# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

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
