# Contributing to agentsync

Thanks for your interest! agentsync is small, dependency-free, and meant to stay that
way. Please read this before opening a PR.

## Principles

- **Stdlib only.** No third-party Python deps. Hooks are bash; the OpenCode plugin is
  plain JS. If you reach for a dependency, reconsider.
- **Mechanism vs policy.** The engine (`core/`) holds zero personal data. Anything
  user-specific belongs in `config/` (git-ignored) or `config.example/`.
- **Determinism over AI.** Repeatable work is a script + a `make`/`mise`/`just`/npm verb,
  never a thing a human must remember. The repo dogfoods this (`make verify`, generated
  docs). Judgment-only work lives in `skills/` as Agent Skills.

## Dev loop

```bash
make verify     # syntax-checks every source + runs the full test suite. Must pass.
```

`make verify` writes nothing to your `$HOME` — tests run against temp sandboxes. CI runs
the same command on every PR.

## Extension points (the common contributions)

- **Add a harness** → use the `add-harness` skill, or by hand: add
  `core/adapters/<name>.py` (subclass `Adapter`, implement `capabilities()` +
  `targets()`), register it in `core/adapters/__init__.py`, add detection in `init.sh`,
  and an assertion in `tests/test_apply.py`. `core/adapters/claude.py` (full) and
  `vscode.py` (instructions-only + its own hooks file) are the two ends to copy from.
- **Add a task runner** for the determinism protocol → extend the four `case` blocks in
  `core/enforcement/_runner.sh` and the `detect()` table in
  `core/enforcement/opencode-plugin.js`.

## Pull requests

- One focused change per PR. Keep diffs minimal.
- `make verify` green, with a test for new logic.
- Match the surrounding style (comment density, naming).

## Roadmap / good first issues

These are wanted but deliberately not built until there's real demand — pick one up:

- **More harnesses** via the `add-harness` skill: Cursor, Windsurf, Zed, Cline, Aider.
- **Generic file-based-harness base** — most new harnesses are just "one instructions
  file + one MCP JSON"; a shared base would shrink those adapters to near-zero code.
- **Project-scope profiles** — today agentsync manages user-scope (global) config; a
  per-repo profile (`.mcp.json`, project instructions/hooks) is a natural extension.
- **Per-harness instruction variants** — the engine renders one `instructions.md` to all
  harnesses; some setups want tool-specific instruction blocks (see Known limitations).
- **Homebrew tap / packaged install** beyond `init.sh`.

## Known limitations (documented, not bugs)

- **One instructions file for all harnesses.** Tool-specific instruction text (e.g. a
  Claude-only note) must currently go into the shared file or be omitted. Tracked above.
- **OpenCode has no rtk integration** — `rtk hook` has no OpenCode processor, so the
  token-killer proxy can't auto-run there. Not fixable from agentsync.
- **The determinism gate is advisory for agents.** It blocks an agent's `git commit` when
  `verify` fails, but a human's manual commit is not gated (by design — see
  `ARCHITECTURE.md`).
