# Global AI assistant instructions

Single source of truth, shared by every AI coding assistant agentsync manages (Claude
Code, GitHub Copilot CLI, OpenCode, VS Code Copilot). Edit here; every tool picks it up
on the next `agentsync apply`. These apply to every project unless a more specific
instruction overrides them.

## Prefer deterministic automation over AI for repeatable work

- **If a task an agent or subagent performs might be repeated, and it can be made
  deterministic (a script, CLI, task runner target, git hook, cron), make it
  deterministic.** Reach for AI only when the work genuinely needs judgment that can't
  be encoded.
- **Why:** deterministic solutions are predictable, reproducible, and — most
  importantly — cost zero model tokens to re-run. Spending tokens to redo work a script
  could do is waste.
- When you notice you (or the user) are about to repeat a manual/AI step, say so and
  offer the script.
- **Where it goes:** put the real work in a shebang'd script, exposed as a standard verb
  (`setup` / `verify` / `test` / `run`) through whatever task runner the repo uses
  (`make`, `mise`, `just`, npm). `verify` is the fast, read-only, commit-safe verb. If
  an agent should call it on its own, wrap it as a Skill that runs that exact verb. A
  step that must *always* run regardless of the model → a hook.
- **Which repo it lives in:** automation specific to one repo lives **in that repo**; if
  a repo has no front door yet, scaffold the standard verbs with `scaffold-determinism`.
  Global/cross-repo tooling lives in your central config repo.

## Prefer CLI tools over MCP servers

- **Always prefer a CLI tool over an MCP server** when both can do the job. CLIs are
  faster, scriptable, leave a reproducible command trail, and don't consume MCP
  context budget. Examples: GitHub MCP → `gh`; Jira/Confluence MCP → `jira`/`acli`;
  MongoDB MCP → `mongosh`; SQL MCP → `psql`/`mysql`/`sqlite3`; cloud MCPs → `aws`/
  `gcloud`/`az`.
- If about to use an MCP that has a CLI, say so, name the CLI, and use the CLI. Only
  fall back to the MCP if no CLI exists or the user explicitly asks for it.
