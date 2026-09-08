#!/usr/bin/env bash
# Isolated executable-contract tests; never imports agmem or touches memory.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
cat > "$fixture/python" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" "$AGMEM_HOOK_SOURCE" "$AGMEM_NO_DAEMON" "$AGMEM_HOOK_TIMEOUT_SEC" "$AGMEM_CONFIG"
cat
SH
chmod +x "$fixture/python"
export AGMEM_PYTHON="$fixture/python"
export AGMEM_CONFIG="$fixture/config.toml"
out=$(printf '{"prompt":"fixture"}' | bash "$repo/agent/memory-hook" distill)
[[ "$out" == *'-m agmem.hooks.distill'* ]]
[[ "$out" == *$'codex\n1\n1.5\n'* ]]
[[ "$out" == *'{"prompt":"fixture"}'* ]]
out=$(printf '{}' | bash "$repo/agent/memory-hook" preserve)
[[ "$out" == *$'codex\n1\n5\n'* ]]
if bash "$repo/agent/memory-hook" invalid > /dev/null 2>&1; then
  printf 'invalid hook unexpectedly accepted\n' >&2; exit 1
fi
AGMEM_PYTHON="$fixture/missing" bash "$repo/agent/memory-hook" capture 2> "$fixture/error"
test -s "$fixture/error"
bash "$repo/agent/memory-hook" --help > /dev/null
printf 'memory-hook: 5 contract checks passed\n'
