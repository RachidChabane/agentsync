# Security Policy

## Reporting a vulnerability

Please report security issues privately via GitHub's **"Report a vulnerability"** button
(Security tab) or by email to **rachid.chabane59@gmail.com**. Do not open a public issue
for vulnerabilities. You'll get an acknowledgement within a few days.

## Scope notes

agentsync edits files under your `$HOME` (AI-assistant config) and, for Claude, imports
MCP servers via the `claude` CLI. Things to be aware of:

- **Your private config never belongs in the engine repo.** `config/` is git-ignored;
  only `config.example/` (generic placeholders) is tracked. Never `git add -f config/`,
  and never push `config/` to a public remote — it holds your real paths, endpoints, and
  plugin set. The included instructions repo state this too.
- **Secrets stay out of config.** MCP auth uses an env-var name + a `headersHelper`
  script path, never a raw key. Keep keys in your environment / the helper script.
- **Hooks run commands.** The determinism gate and any hooks you add in `overrides.json`
  execute shell on tool use. Review hooks before applying, as you would any shell config.
- **`agentsync apply` is reversible** via `agentsync uninstall` (and `.bak` snapshots),
  but treat it like any tool that writes to your dotfiles.
