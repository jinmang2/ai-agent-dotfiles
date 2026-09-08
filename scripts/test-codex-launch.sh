#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -r "$TMP"' EXIT

mkdir -p "$TMP/home/.local/bin"

cat > "$TMP/home/.local/bin/codex" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "${AGENT_PROFILE:-}" > "$TEST_CODEX_PROFILE"
printf '%s\n' "$*" > "$TEST_CODEX_ARGS"
exit "${CODEX_EXIT:-0}"
SH
chmod +x "$TMP/home/.local/bin/codex"

cat > "$TMP/home/.local/bin/agent-codex-hud-launcher" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = --stop ]; then
  printf '%%hud\n' > "$TEST_KILLED_PANE"
  exit 0
fi
printf '%s\n' "${AGENT_PROFILE:-}" > "$TEST_LAUNCHER_PROFILE"
SH
chmod +x "$TMP/home/.local/bin/agent-codex-hud-launcher"

cat > "$TMP/home/.local/bin/tmux" <<'SH'
#!/usr/bin/env bash
case "${1:-}" in
  list-panes)
    printf '%%parent\n'
    if [ "${TEST_EXISTING_HUD:-0}" = "1" ]; then
      printf '%%hud\n'
    fi
    ;;
  kill-pane)
    echo 'Unexpected pane deletion' >&2
    exit 99
    ;;
esac
SH
chmod +x "$TMP/home/.local/bin/tmux"

cat > "$TMP/run-codex.sh" <<SH
#!/usr/bin/env bash
set -euo pipefail
. "$REPO/shell/agents.sh"
codex "\$@"
SH
chmod +x "$TMP/run-codex.sh"

reset_logs() {
  rm -f "$TMP"/launcher-profile "$TMP"/codex-profile "$TMP"/codex-args "$TMP"/killed-pane
}

run_plain() {
  env \
    HOME="$TMP/home" \
    PATH="$TMP/home/.local/bin:$PATH" \
    TMUX_PANE="%parent" \
    TEST_LAUNCHER_PROFILE="$TMP/launcher-profile" \
    TEST_CODEX_PROFILE="$TMP/codex-profile" \
    TEST_CODEX_ARGS="$TMP/codex-args" \
    TEST_KILLED_PANE="$TMP/killed-pane" \
    "$@"
}

run_pty() {
  local cmd
  printf -v cmd '%q ' env \
    HOME="$TMP/home" \
    PATH="$TMP/home/.local/bin:$PATH" \
    TMUX_PANE="%parent" \
    TEST_LAUNCHER_PROFILE="$TMP/launcher-profile" \
    TEST_CODEX_PROFILE="$TMP/codex-profile" \
    TEST_CODEX_ARGS="$TMP/codex-args" \
    TEST_KILLED_PANE="$TMP/killed-pane" \
    "$@"
  script -q -e -c "$cmd" /dev/null >/dev/null
}

assert_file() {
  [ -f "$1" ] || { printf 'missing file: %s\n' "$1" >&2; exit 1; }
}

assert_no_file() {
  [ ! -f "$1" ] || { printf 'unexpected file: %s\n' "$1" >&2; exit 1; }
}

assert_eq() {
  [ "$1" = "$2" ] || { printf 'expected [%s], got [%s]\n' "$2" "$1" >&2; exit 1; }
}

reset_logs
run_pty bash "$TMP/run-codex.sh"
assert_eq "$(cat "$TMP/launcher-profile")" "codex"
assert_eq "$(cat "$TMP/codex-profile")" "codex"
assert_eq "$(cat "$TMP/killed-pane")" "%hud"

reset_logs
run_pty env AGENT_PROFILE=custom bash "$TMP/run-codex.sh" resume
assert_eq "$(cat "$TMP/launcher-profile")" "custom"
assert_eq "$(cat "$TMP/codex-profile")" "custom"
assert_eq "$(cat "$TMP/codex-args")" "resume"
assert_eq "$(cat "$TMP/killed-pane")" "%hud"

reset_logs
run_pty bash "$TMP/run-codex.sh" exec echo ok
assert_no_file "$TMP/launcher-profile"
assert_eq "$(cat "$TMP/codex-args")" "exec echo ok"
assert_no_file "$TMP/killed-pane"

reset_logs
run_pty bash "$TMP/run-codex.sh" --help
assert_no_file "$TMP/launcher-profile"
assert_eq "$(cat "$TMP/codex-args")" "--help"
assert_no_file "$TMP/killed-pane"

reset_logs
run_pty bash "$TMP/run-codex.sh" doctor
assert_no_file "$TMP/launcher-profile"
assert_eq "$(cat "$TMP/codex-args")" "doctor"
assert_no_file "$TMP/killed-pane"

reset_logs
run_pty bash "$TMP/run-codex.sh" e
assert_no_file "$TMP/launcher-profile"
assert_eq "$(cat "$TMP/codex-args")" "e"
assert_no_file "$TMP/killed-pane"

reset_logs
run_pty bash "$TMP/run-codex.sh" --model gpt-5.5
assert_eq "$(cat "$TMP/launcher-profile")" "codex"
assert_eq "$(cat "$TMP/codex-args")" "--model gpt-5.5"
assert_eq "$(cat "$TMP/killed-pane")" "%hud"

reset_logs
run_pty bash "$TMP/run-codex.sh" --model gpt-5.5 exec
assert_no_file "$TMP/launcher-profile"
assert_eq "$(cat "$TMP/codex-args")" "--model gpt-5.5 exec"
assert_no_file "$TMP/killed-pane"

reset_logs
run_pty bash "$TMP/run-codex.sh" -c profile exec
assert_no_file "$TMP/launcher-profile"
assert_eq "$(cat "$TMP/codex-args")" "-c profile exec"
assert_no_file "$TMP/killed-pane"

reset_logs
run_pty bash "$TMP/run-codex.sh" resume --help
assert_no_file "$TMP/launcher-profile"
assert_eq "$(cat "$TMP/codex-args")" "resume --help"
assert_no_file "$TMP/killed-pane"

reset_logs
run_pty env CODEX_HUD=0 bash "$TMP/run-codex.sh"
assert_no_file "$TMP/launcher-profile"
assert_file "$TMP/codex-profile"
assert_no_file "$TMP/killed-pane"

reset_logs
run_pty env CODEX_COMPANION_HUD_ACTIVE=1 bash "$TMP/run-codex.sh"
assert_no_file "$TMP/launcher-profile"
assert_file "$TMP/codex-profile"
assert_no_file "$TMP/killed-pane"

reset_logs
run_pty env TEST_EXISTING_HUD=1 bash "$TMP/run-codex.sh" fork
assert_eq "$(cat "$TMP/launcher-profile")" "codex"
assert_eq "$(cat "$TMP/codex-args")" "fork"
assert_eq "$(cat "$TMP/killed-pane")" "%hud"

reset_logs
run_plain bash "$TMP/run-codex.sh"
assert_no_file "$TMP/launcher-profile"
assert_file "$TMP/codex-profile"
assert_no_file "$TMP/killed-pane"

reset_logs
set +e
run_pty env CODEX_EXIT=37 bash "$TMP/run-codex.sh"
status=$?
set -e
assert_eq "$status" "37"
assert_eq "$(cat "$TMP/killed-pane")" "%hud"
