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
  `vscode.py` (instructions-only + its own hooks file) are the two ends to copy from —
  and if the tool is just "one instructions file + one MCP JSON", subclass `FileHarness`
  instead (`windsurf.py` is the model: paths + an MCP entry renderer).
- **Add a task runner** for the determinism protocol → extend the four `case` blocks in
  `core/enforcement/_runner.sh` and the `detect()` table in
  `core/enforcement/opencode-plugin.js`.

## Pull requests

- One focused change per PR. Keep diffs minimal.
- `make verify` green, with a test for new logic.
- Match the surrounding style (comment density, naming).

## Roadmap / good first issues

These are wanted but deliberately not built until there's real demand — pick one up:

- **More harnesses** via the `add-harness` skill (Cursor, Windsurf, Zed and Cline
  shipped on the `FileHarness` base; most new tools are ~10 lines).
- **Homebrew tap** — needs a tagged release plus a separate tap repo; `pipx install`
  (see `pyproject.toml`) covers no-clone installs meanwhile.

## Known limitations (documented, not bugs)

- **Cursor global rules are unmanageable** — they live in Cursor's settings UI, not a
  file; only its MCP (and project-scope AGENTS.md) can be rendered.
- **Zed MCP is unmanaged** — `context_servers` lives inside Zed's JSONC `settings.json`;
  a stdlib-json merge would destroy user comments, so the adapter is instructions-only.
- **No Aider adapter** — Aider has no native MCP and its only persistent config is YAML
  (`~/.aider.conf.yml`), which a stdlib-only engine can't merge safely.
- **OpenCode has no rtk integration** — `rtk hook` has no OpenCode processor, so the
  token-killer proxy can't auto-run there. Not fixable from agentsync.
- **The determinism gate is advisory for agents.** It blocks an agent's `git commit` when
  `verify` fails, but a human's manual commit is not gated (by design — see
  `ARCHITECTURE.md`).
