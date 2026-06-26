#!/usr/bin/env bash
# Deterministic half of `author-verify`: scan the current repo for fast quality tools and
# print CANDIDATE verify commands. It does not decide — the LLM picks which candidates are
# real, fast, and read-only, and writes them into the repo's `verify` verb.
#
# Run inside the target repo:  bash skills/author-verify/detect-tools.sh
set -u
have() { command -v "$1" >/dev/null 2>&1; }
exists() { for f in "$@"; do [ -e "$f" ] && return 0; done; return 1; }
say() { printf '  candidate: %-28s (%s)\n' "$1" "$2"; }

echo "detected runner:"
src="$(dirname "$(dirname "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")")/core/enforcement/_runner.sh"
[ -f "$src" ] && { . "$src"; r="$(det_runner)"; echo "  ${r:-none} (verify goes here)"; } || echo "  (runner lib not found)"

echo "fast checks found:"
# Python
if exists pyproject.toml ruff.toml .ruff.toml || have ruff; then have ruff && say "ruff check ." "python lint"; fi
{ grep -qs "\[tool.mypy\]" pyproject.toml || exists mypy.ini .mypy.ini; } && have mypy && say "mypy ." "python types"
{ grep -qs "\[tool.black\]" pyproject.toml || have black; } && have black && say "black --check ." "python format"
# JS / TS
exists tsconfig.json && say "npx tsc --noEmit" "typescript typecheck"
exists .eslintrc .eslintrc.js .eslintrc.json eslint.config.js && say "npx eslint ." "js/ts lint"
if exists package.json; then
  grep -qs '"lint"' package.json && say "npm run lint" "package.json lint script"
  grep -qs '"typecheck"' package.json && say "npm run typecheck" "package.json typecheck script"
fi
# Go
exists go.mod && { say "go vet ./..." "go vet"; say "test -z \"\$(gofmt -l .)\"" "go format"; }
# Rust
exists Cargo.toml && { say "cargo clippy -- -D warnings" "rust lint"; say "cargo fmt --check" "rust format"; }
# Shell
if ls ./*.sh >/dev/null 2>&1 && have shellcheck; then say "shellcheck *.sh" "shell lint"; fi

echo "note: keep verify FAST and READ-ONLY (it runs at commit time). Slow/full suites go under 'test'."
