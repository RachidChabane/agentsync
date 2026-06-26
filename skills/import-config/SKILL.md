---
name: import-config
description: Reverse-engineer an existing hand-maintained AI config (Claude Code / Copilot / OpenCode / VS Code) into an agentsync config/, then prove nothing is lost. Use to migrate onto agentsync without rebuilding config by hand.
---

# Import an existing config into agentsync

Turning a live, hand-built setup into a `config/` is **judgment** (dedup, decide what's
core vs passthrough, find skill sources) made **safe** by a deterministic diff-proof. Do
not switch the user's real config until `diff-prove.sh` is clean.

## 1. Read the live config (resolve symlinks to the real source)
- **Claude** — `~/.claude/settings.json`, `~/.claude/CLAUDE.md` (follow `@imports`),
  MCP via `claude mcp list` / `~/.claude.json`, skills in `~/.claude/skills/` (note where
  each symlinks to — that's its source).
- **Copilot** — `~/.copilot/{settings.json, mcp-config.json, copilot-instructions.md}`,
  `~/.copilot/skills/`.
- **OpenCode** — `~/.config/opencode/opencode.json`.
- **VS Code** — `Code/User/settings.json` (instructions + hook locations).

## 2. Synthesize `config/` (the judgment)
- `instructions.md` — the shared instruction text (merge per-tool variants into one).
- `skills.json` — tier per skill (from `skillOverrides` / `disabledSkills` /
  `permission.skill`). Where a skill dir symlinks to a real source, record `source` (+
  `subpath`) so agentsync manages it; for git-backed skill repos use the git URL.
- `mcp.json` — the union of MCP servers across tools, **deduped** by identity (same
  server defined per-tool collapses to one). Mark secret-bearing ones with `auth`.
- `profile.json` — the harnesses in use.
- `overrides.json` — everything agentsync's four core concerns don't cover but the live
  config sets: plugins/marketplaces, status line, model effort, custom notification
  hooks (under `hooks`, merged additively), editor prefs. This catches what would
  otherwise be lost.

## 3. Prove nothing is lost (deterministic — required)
```
bash skills/import-config/diff-prove.sh
```
It applies `config/` into a sandbox seeded with the live files and diffs the result
against the originals. **Iterate `config/` until it prints CLEAN.** A `DIFF` means a key
or hook the live config has isn't reproduced — usually something to add to
`overrides.json`. Don't proceed on any unexplained diff.

## 4. Only then switch
With a clean diff-proof, the real `agentsync apply` is safe — every change it would make
is already accounted for. Keep the old config repo as rollback until you've run a session
in each harness. `agentsync uninstall` reverts agentsync's changes if needed.
