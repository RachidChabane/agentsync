#!/usr/bin/env bash
# Copilot CLI userPromptSubmitted hook. Copilot's sessionStart can't inject context, so
# we use userPromptSubmitted — but it fires on every prompt, so we inject the nudge ONCE
# per session (sentinel keyed on sessionId). Emits TOP-LEVEL additionalContext (Copilot
# does NOT read the hookSpecificOutput wrapper). Always exits 0.
set +e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_msg.sh"

input=""; [ ! -t 0 ] && input="$(cat 2>/dev/null)"
sid="$(printf '%s' "$input" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("sessionId",""))
except Exception: pass' 2>/dev/null)"
sentinel="${TMPDIR:-/tmp}/det-copilot-${sid:-nosession}"
[ -n "$sid" ] && [ -e "$sentinel" ] && exit 0          # already nudged this session

det_cd_from "$input"
msg="$(det_build_msg)"
[ -n "$msg" ] || exit 0
[ -n "$sid" ] && : > "$sentinel" 2>/dev/null
python3 -c 'import json,sys;print(json.dumps({"additionalContext":sys.argv[1]}))' "$msg" 2>/dev/null
exit 0
