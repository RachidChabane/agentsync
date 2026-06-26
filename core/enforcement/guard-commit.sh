#!/usr/bin/env bash
# PreToolUse commit gate (Claude Code / VS Code Copilot / Copilot CLI). Before an agent
# runs `git commit`, run the repo's fast `verify` verb through whatever task runner the
# repo uses, and BLOCK (exit 2) only on a clean verify failure.
#
# Fails OPEN (exit 0) on everything else — no runner, no `verify` verb, timeout, own
# breakage — so it can never wedge a repo. Reads the command from either stdin schema:
# Claude/VS Code `.tool_input.command`, or Copilot CLI `.toolArgs` (a JSON-encoded
# string) -> `.command`. Only ever exits 0 or 2 (correct on fail-closed harnesses too).
# Do NOT wrap in `|| true`: that swallows exit 2.
set +e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_runner.sh"

run_to() {  # portable timeout: macOS has no `timeout`; fall back to gtimeout, then perl
  local s="$1"; shift
  if   command -v timeout  >/dev/null 2>&1; then timeout  "$s" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$s" "$@"
  else perl -e 'alarm shift; exec @ARGV' "$s" "$@"; fi
}

input=""; [ ! -t 0 ] && input="$(cat 2>/dev/null)"
[ -n "$input" ] || exit 0

# Extract cwd + whether the command is a git commit, in python (handles both schemas),
# returned as shell-quoted assignments for a safe eval.
eval "$(printf '%s' "$input" | python3 -c '
import json,sys,shlex
try: d=json.load(sys.stdin)
except Exception: d={}
cmd=""
ti=d.get("tool_input")
if isinstance(ti,dict): cmd=ti.get("command","") or ""
if not cmd:
    ta=d.get("toolArgs")
    if isinstance(ta,str):
        try: cmd=json.loads(ta).get("command","") or ""
        except Exception: pass
    elif isinstance(ta,dict): cmd=ta.get("command","") or ""
print("WD="+shlex.quote(d.get("cwd","") or ""))
print("ISCOMMIT=%d" % (1 if "git commit" in cmd else 0))
' 2>/dev/null)"

[ "${ISCOMMIT:-0}" = "1" ] || exit 0
[ -n "${WD:-}" ] && [ -d "$WD" ] && cd "$WD" 2>/dev/null

r="$(det_runner)"; [ -n "$r" ] || exit 0          # no front door -> fail open
det_has_verb "$r" verify || exit 0                # no verify verb -> fail open

out="$(run_to 120 bash -c '. "'"$DIR"'/_runner.sh"; det_run "'"$r"'" verify' 2>&1)"; rc=$?
case "$rc" in
  0)        exit 0 ;;
  124|142)  exit 0 ;;   # timed out -> fail open
  *) printf 'Commit blocked: `verify` (%s) failed — fix before committing.\n\n%s\n' "$r" "$out" >&2
     exit 2 ;;
esac
