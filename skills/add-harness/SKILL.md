---
name: add-harness
description: Add support for a new AI coding harness (Cursor, Windsurf, Zed, Aider, …) to agentsync. Use when a tool you want to manage isn't in core/adapters/. Reads the harness's docs, scaffolds the adapter, and verifies it.
---

# Add a harness to agentsync

Adding a harness is **judgment work** (mapping the harness's config concepts) wrapped
around a **deterministic scaffold**. Do the steps in order; don't skip the doc-reading.

## 1. Check it isn't already handled
Look in `core/adapters/__init__.py` (`ADAPTERS`) and `config/profile.json`. If the
harness is there, stop — there's nothing to add.

## 2. Scaffold the adapter (deterministic)
```
python3 skills/add-harness/scaffold-adapter.py <name>
```
This writes `core/adapters/<name>.py` (stubbed) and registers it. It does NOT know the
harness — you fill that in next.

## 3. Read the harness's docs (the judgment — do not guess)
Find and confirm, from the harness's own documentation:
- **Instructions** — does it read a user-scope instructions/rules file? Where? (If only
  inline in settings, mirror VS Code's approach.)
- **MCP** — its MCP config format and file location (or that it has none).
- **Skills/permissions** — any skill-availability control (or none).
- **Enforcement (hooks)** — *the* tricky part: can it run a command before a tool call?
  What JSON does the hook get on stdin (the command field name)? How does it signal
  "block"? If it has no hook surface but has a plugin system, mirror OpenCode's plugin.
  If it can't enforce at all, leave `enforcement` out of `capabilities()`.

## 4. Fill the adapter
Implement `capabilities()` (honestly — only what the harness actually supports) and
`targets()` using the existing target types (`Link`, `Json`, `Merge`, `HookSpec`). Reuse
the shared `core/enforcement/guard-commit.sh` and `session-nudge.sh` — point the
harness's hook at them per its contract; don't re-implement the gate. Keep
`extra_owned`/`extra_hooks` from `self._passthrough(ctx)` so settings passthrough works.

## 5. Detection + test + verify
- Add a detection line for it in `init.sh`.
- Add assertions to `tests/test_apply.py` (its files render correctly in the sandbox).
- Run `make verify`. It must pass before you're done.

## Reference
`core/adapters/claude.py` (full-featured) and `vscode.py` (instructions-only, reuses
another harness's hooks) are the two ends of the spectrum to copy from.
