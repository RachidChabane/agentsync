#!/usr/bin/env bash
# Runner abstraction for the determinism protocol's front door.
#
# The PORTABLE convention is the verb set (setup / verify / test / run, per GitHub's
# "Scripts to Rule Them All"). The task RUNNER is just a binding — we detect whichever
# one the repo already uses, so the protocol is tool-agnostic instead of locked to one.
# Add a runner by extending the four case statements below; nothing else changes.
#
# Sourced, not executed. Exposes:
#   det_runner            -> echo the runner id (mise|make|just|npm) or "" if none
#   det_has_verb <r> <v>  -> exit 0 if verb <v> exists in runner <r>
#   det_run     <r> <v>   -> run verb <v> through runner <r> (stdout+stderr inherited)
#   det_list    <r>       -> echo a human-readable task list (for the nudge)

det_runner() {
  if   { [ -f mise.toml ] || [ -f .mise.toml ]; } && command -v mise >/dev/null 2>&1; then echo mise
  elif { [ -f Makefile ] || [ -f makefile ] || [ -f GNUmakefile ]; } && command -v make >/dev/null 2>&1; then echo make
  elif { [ -f justfile ] || [ -f Justfile ] || [ -f .justfile ]; } && command -v just >/dev/null 2>&1; then echo just
  elif [ -f package.json ] && command -v npm >/dev/null 2>&1; then echo npm
  else echo ""; fi
}

det_has_verb() {  # det_has_verb <runner> <verb>
  local r="$1" v="$2"
  case "$r" in
    mise) mise tasks 2>/dev/null | grep -qE "^$v( |\$)" ;;
    make) make -n "$v" >/dev/null 2>&1 ;;                       # -n = dry-run: 0 iff target exists
    just) just --show "$v" >/dev/null 2>&1 ;;
    npm)  node -e 'process.exit((((require("./package.json").scripts)||{})[process.argv[1]])?0:1)' "$v" >/dev/null 2>&1 ;;
    *) return 1 ;;
  esac
}

det_run() {  # det_run <runner> <verb>
  local r="$1" v="$2"
  case "$r" in
    mise) mise run "$v" ;;
    make) make "$v" ;;
    just) just "$v" ;;
    npm)  npm run --silent "$v" ;;
    *) return 0 ;;
  esac
}

det_list() {  # det_list <runner>
  local r="$1"
  case "$r" in
    mise) mise tasks 2>/dev/null ;;
    make) make help 2>/dev/null || grep -hE '^[a-zA-Z0-9_.-]+:' Makefile makefile GNUmakefile 2>/dev/null | sed 's/:.*//' | sort -u ;;
    just) just --list 2>/dev/null ;;
    npm)  node -e 'console.log(Object.keys((require("./package.json").scripts)||{}).join("\n"))' 2>/dev/null ;;
    *) : ;;
  esac
}
