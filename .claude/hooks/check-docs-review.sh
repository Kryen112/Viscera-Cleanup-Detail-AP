#!/usr/bin/env bash
# Stop hook. When the ending turn edited apworld Python or mod source, block
# the stop once and remind the agent to run the code-reviewer and to check
# the docs for drift. Plain sed and grep only, so it runs on any Git Bash.
set -u

input=$(cat)

transcript=$(printf '%s' "$input" | sed -n 's/.*"transcript_path":"\([^"]*\)".*/\1/p')
transcript=$(printf '%s' "$transcript" | sed 's/\\\\/\//g')
[ -n "$transcript" ] && [ -f "$transcript" ] || exit 0

session=$(printf '%s' "$input" | sed -n 's/.*"session_id":"\([^"]*\)".*/\1/p')
[ -n "$session" ] || session=unknown

# Every stop advances the per-session line marker, so each transcript line is
# scanned exactly once and old changes never re-fire.
state_dir="${TMPDIR:-${TEMP:-/tmp}}/claude-vcd-stop-hook"
mkdir -p "$state_dir"
state_file="$state_dir/$session"
last=0
[ -f "$state_file" ] && last=$(cat "$state_file")
case "$last" in '' | *[!0-9]*) last=0 ;; esac
total=$(wc -l < "$transcript")
printf '%s' "$total" > "$state_file"

# A stop that is already continuing from this hook passes through, so the
# reminder fires at most once per turn.
case "$input" in
  *'"stop_hook_active":true'*) exit 0 ;;
esac

[ "$total" -gt "$last" ] || exit 0

# A transcript line holds one whole message, so an edit shows its tool name
# and its file path on the same line. The path must sit inside the file_path
# field itself, or edits whose content merely mentions a watched path would
# fire the reminder. Paths appear JSON-escaped, hence the doubled backslash
# alternative.
if tail -n +"$((last + 1))" "$transcript" \
  | grep -E '"name" *: *"(Write|Edit|NotebookEdit)"' \
  | grep -qE '"file_path" *: *"[^"]*VCD_AP(/|\\\\)(apworld(/|\\\\)[^"]*\.py"|mod(/|\\\\)[^"]*\.uc")'; then
  cat <<'JSON'
{"decision": "block", "reason": "This turn changed apworld Python or mod source. Before finishing, run the code-reviewer subagent on the diff and address blockers, and check for documentation drift per CLAUDE.md: VCD_AP/docs (PLAYER_SETUP.md, RELEASE_NOTES.md), the regenerated options template, and the build state in plans/V1_PLAN.md. If the review and the docs pass already happened this turn, or the change was not player-visible, say so and finish."}
JSON
fi
exit 0
