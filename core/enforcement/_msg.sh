#!/usr/bin/env bash
# Shared helpers for the determinism hooks (sourced, not executed). One copy of the
# per-repo message + cwd logic so the per-harness hooks can't drift apart.
DIR_MSG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR_MSG/_runner.sh"

# det_cd_from "<hook stdin json>" : cd into the workspace the harness reported in `cwd`
# (some harnesses run hooks outside the repo; harmless where cwd is already right).
det_cd_from() {
  local wd
  wd="$(printf '%s' "${1:-}" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("cwd",""))
except Exception: pass' 2>/dev/null)"
  [ -n "$wd" ] && [ -d "$wd" ] && cd "$wd" 2>/dev/null
  return 0
}

# det_build_msg : print the per-repo determinism nudge, or nothing when not applicable
# (not a git repo). Uses the current working directory and whichever runner is present.
det_build_msg() {
  command -v git >/dev/null 2>&1 || return 0
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
  local r; r="$(det_runner)"
  if [ -n "$r" ]; then
    local tasks; tasks="$(det_list "$r")"
    [ -n "$tasks" ] || return 0
    printf 'Determinism protocol — this repo'\''s deterministic front door (%s). Prefer these over re-deriving work or running ad-hoc equivalents:\n\n%s\n' "$r" "$tasks"
  else
    printf '%s\n' "Determinism protocol: this repo has no deterministic front door yet. Any repeatable op specific to THIS repo belongs in a repo-local task (real work in a script, exposed as a make/mise/just/npm verb); global/cross-repo tooling lives in your config repo. Scaffold the standard verbs with: scaffold-determinism"
  fi
}
