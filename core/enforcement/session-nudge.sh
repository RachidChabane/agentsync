#!/usr/bin/env bash
# SessionStart hook (Claude Code / VS Code Copilot). Surfaces the determinism protocol
# per repo: lists the repo's tasks if it has a front door, else nudges to scaffold.
#
# Emits {"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":...}}
# — Claude accepts it and extracts the string; VS Code REQUIRES it (raw stdout there is
# a JSON parse error). (Copilot CLI's sessionStart can't inject — it uses a separate
# userPromptSubmitted hook, see prompt-context.sh.) No-op outside a git repo. Always 0.
set +e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_msg.sh"

input=""; [ ! -t 0 ] && input="$(cat 2>/dev/null)"   # read stdin only if piped
det_cd_from "$input"

msg="$(det_build_msg)"
[ -n "$msg" ] || exit 0
python3 -c 'import json,sys;print(json.dumps({"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":sys.argv[1]}}))' "$msg" 2>/dev/null \
  || printf '%s\n' "$msg"
exit 0
