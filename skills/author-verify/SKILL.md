---
name: author-verify
description: Fill in a repo's `verify` verb with its real fast checks (lint, typecheck, format). Use after scaffold-determinism creates a stub verify, or when a repo's commit gate has no real checks yet.
---

# Author a repo's `verify` verb

The determinism commit gate runs `verify` before every agent commit. A stub `verify`
that just passes gives no protection; the right checks are **judgment** (which of this
repo's tools are fast and read-only) over a **deterministic scan**.

## 1. Scan for candidates (deterministic)
```
bash skills/author-verify/detect-tools.sh
```
It prints the repo's task runner and candidate fast checks (ruff, mypy, tsc, eslint, go
vet, clippy, shellcheck, package.json scripts, …).

## 2. Decide (judgment)
Keep only checks that are **fast** and **read-only/non-destructive** — `verify` runs at
commit time. Anything slow (full test suite, integration, e2e) belongs under `test`, not
`verify`. Confirm each tool is actually configured for this repo, not just installed.

## 3. Write it into the front door
Put the chosen commands in the repo's `verify` verb, in whatever runner it uses:
- `Makefile` → the `verify:` recipe
- `mise.toml` → `[tasks.verify]`
- `justfile` → `verify:`
- `package.json` → `"scripts": { "verify": "..." }`

Chain commands so any failure fails the verb (e.g. `ruff check . && mypy .`). If the repo
has no front door yet, run `scaffold-determinism` first.

## 4. Prove it gates
Run the verb (`make verify` / `mise run verify` / …): it should pass on clean code.
Introduce a deliberate lint error and confirm it now fails — that's what blocks a bad
commit. Revert the error.
