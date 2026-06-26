#!/usr/bin/env bash
# Deterministic scaffolder (installed on PATH as `scaffold-determinism`). Run inside any
# repo to give it the standard deterministic front door — the standard verbs (setup /
# verify / test / run) on whichever task runner you pick. One-command adoption of the
# determinism protocol; afterwards the SessionStart and commit hooks arm automatically.
#
#   scaffold-determinism            # default runner: make (universal, no install)
#   scaffold-determinism --mise     # mise.toml
#   scaffold-determinism --just     # justfile
#
# The standard is the VERB SET, not the runner; this just writes one binding of it.
set -euo pipefail

runner="make"
case "${1:-}" in
  --make|"") runner="make" ;;
  --mise)    runner="mise" ;;
  --just)    runner="just" ;;
  -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown option: $1 (use --make | --mise | --just)" >&2; exit 1 ;;
esac

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "Not inside a git repo. cd into the repo first." >&2; exit 1; }

exists() { for f in "$@"; do [ -e "$f" ] && return 0; done; return 1; }

case "$runner" in
  make)
    exists Makefile makefile GNUmakefile && { echo "Makefile already exists — not overwriting." >&2; exit 0; }
    cat > Makefile <<'EOF'
# Deterministic front door for THIS repo (determinism > AI: prefer scripts over
# re-deriving repeatable work with the model — cheaper, predictable, testable).
# Keep recipes thin; put real work in script/. `make help` lists verbs.
.PHONY: help setup verify test run

help:  ## list verbs
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?## "}{printf "  %-8s %s\n",$$1,$$2}'

setup:  ## install deps / bootstrap
	@echo 'TODO: setup'; exit 1

# 'verify' = fast, read-only, commit-safe. The commit gate runs this and blocks the
# commit if it fails — keep it quick and never destructive.
verify:  ## fast read-only checks (lint, typecheck, drift) — runs at commit time
	@echo 'verify: no checks defined yet — add them in the Makefile'

test:  ## full test suite (slow — kept out of the commit gate)
	@echo 'TODO: tests'; exit 1

run:  ## start the app
	@echo 'TODO: run'; exit 1
EOF
    echo "Created Makefile with standard verbs (setup / verify / test / run). 'make help' lists them." ;;
  mise)
    exists mise.toml .mise.toml && { echo "mise.toml already exists — not overwriting." >&2; exit 0; }
    cat > mise.toml <<'EOF'
# Deterministic front door for THIS repo. Keep tasks thin; real work in script/.
# `mise tasks` lists them. 'verify' is fast/read-only and runs at commit time.
[tasks.setup]
description = "Install deps / bootstrap the repo"
run = "echo 'TODO: setup'; exit 1"
[tasks.verify]
description = "Fast read-only checks (lint, typecheck, drift) — runs at commit time"
run = "echo 'verify: no checks defined yet — add them in mise.toml'"
[tasks.test]
description = "Full test suite (slow — kept out of the commit gate)"
run = "echo 'TODO: tests'; exit 1"
[tasks.run]
description = "Start the app"
run = "echo 'TODO: run'; exit 1"
EOF
    echo "Created mise.toml with standard verbs. 'mise tasks' lists them." ;;
  just)
    exists justfile Justfile .justfile && { echo "justfile already exists — not overwriting." >&2; exit 0; }
    cat > justfile <<'EOF'
# Deterministic front door for THIS repo. Keep recipes thin; real work in script/.
# `just --list` lists them. 'verify' is fast/read-only and runs at commit time.
setup:
	@echo 'TODO: setup'; exit 1
# fast read-only checks — runs at commit time
verify:
	@echo 'verify: no checks defined yet — add them in the justfile'
test:
	@echo 'TODO: tests'; exit 1
run:
	@echo 'TODO: run'; exit 1
EOF
    echo "Created justfile with standard verbs. 'just --list' lists them." ;;
esac

echo "Next: put real commands in the verbs you need; real work goes in script/<verb>."
echo "The commit gate runs 'verify'."
