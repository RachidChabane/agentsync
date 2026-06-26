# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

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
