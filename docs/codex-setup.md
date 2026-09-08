# Codex personal setup

## Current status (2026-09-08)

The fixed row worked in the existing session and isolated tests, but the user subsequently reported no HUD in newly opened sessions. This remains unresolved: the actual failing launch path has not been reproduced or diagnosed. Earlier completion statements apply to the tested surface only, not universal startup/re-entry reliability. See [change history and open issues](codex-changes.md).

Prefix-free F8 and a native-footer-first layout with always-visible supplemental facts were recommendations only. No shortcut or layout changes from that recommendation have been applied; the implemented popup shortcut remains Alt+a, then h.

## Ownership

Codex owns ChatGPT authentication, Apps, and the native context/cost/limit footer. OMX owns orchestration. OMO supplies development tools; its overlapping continuation hooks can be disabled through native hook state in `config.toml`, without editing the plugin cache. Existing Claude HUD rendering is unchanged.

The HUD uses a fixed tmux status row above the existing tab list, not a separate pane. Codex's native footer remains the authority for current context and account limits. Detailed local session facts are available in the popup (Alt+a, then h with this repository's tmux prefix).

In interactive tmux, the shell wrapper registers the pane before the first prompt. Native `SessionStart` binds its exact session ID and transcript when the first turn begins. Until then, session metrics remain unknown rather than borrowing another session in the same directory. `SessionEnd --stop` unregisters the pane. Repeated registration is idempotent; migration removes only the old HUD pane carrying the matching ownership marker. Other windows retain their ordinary tab row. Set `CODEX_HUD=0` to opt out; outside tmux the hook is a no-op. For direct checks:

```bash
agent-codex-hud --detail --pane "$TMUX_PANE"
agent-codex-hud --json --pane "$TMUX_PANE"
agent-codex-hud-launcher --popup
```

The fixed row prioritizes context remaining, reported account limits and `obs` (age of the last observed token event). Wider terminals add cumulative tokens, cache hit rate, model and session information. Narrow terminals omit lower-priority fields; they do not create another pane. The native footer prioritizes context, five-hour and weekly limits before tokens, estimated cost and branch.

The popup groups usage, activity, health and metadata. Scroll with arrows or PageUp/PageDown and close with `q`. Agent entries are up to eight recently updated child relationships: `8 shown` is not a running-agent count, and `edge:open` is a database relationship status. Task counts remain unavailable without a reliable session-scoped source. Memory `ready` means the daemon answered its health check; recall/save are separately `not observed`, not assumed successful. MCP connection health is not inferred from this row.

Session facts come only from the bound pane's rollout and exact read-only SQLite thread row. OMX information additionally requires an exact session ID and working-directory match. Missing values remain unknown; cumulative token totals are never used as a substitute for current context usage.

Fixed-row verification (2026-09-08): 22 HUD Python tests, isolated lifecycle/re-entry/launch checks, type/lint checks and two independent reviews of all 17 PTY-rendered screens passed. These checks did not establish every real new-session launch path. A publishable summary and repeatable commands are in the [change history](codex-changes.md). Local screenshot/runtime evidence is not distributed in this repository. The split-pane results below are historical.

## Shared memory

`agent-memory-daemon` starts the existing agentic-memory installation with the `experience` organizer and no idle shutdown. The user service listens only on `127.0.0.1:8765`. It uses `~/.agmem/agmem.toml`; credentials stay in that private file.

```bash
systemctl --user daemon-reload
systemctl --user enable --now agentic-memory.service
curl --fail --max-time 2 http://127.0.0.1:8765/health
```

First startup loads the existing embedding model; `active (running)` does not mean HTTP is ready yet. On the audited machine, memory settled near 1.9 GB. The service is enabled for the user session; this setup does not enable systemd lingering or expose the daemon on the network.

Codex hooks use `agent-memory-hook` to set the same config and default `main` namespace, mark captures as `codex`, and prevent competing hook-spawned daemons. Claude's machine overlay now also sets `AGMEM_NO_DAEMON=1`; its existing memory hooks and HUD settings are preserved.

Codex's shutdown hook gets a 1.5-second HTTP request budget within its 3-second native hook limit. Preserve/recall/capture retain the normal 5-second wrapper request budget inside their native hook limits. Failed deliveries must take the existing local preservation path; do not test by writing synthetic conversations into the real `main` store.

The daemon and wrapper both default to namespace `main`, but the fixed HTTP MCP configuration does not make each request namespace-scoped by itself. Use an isolated daemon or explicit test namespace when validating memory writes.

If capture was accepted by the daemon but its reply times out, the local retry can duplicate that prompt. Preserve/distill use the existing spool/idempotent ingestion path. The timeout bounds the HTTP request, not all Python startup overhead; the isolated shutdown smoke completed in 1.73 seconds on this machine.

## Backups and recovery

Configuration installation must preserve unrelated model, security, authentication, project-trust and plugin settings. Apply is idempotent and creates private backups before changing live Codex files. It does not invent hook trust hashes or globally bypass hook trust.

Use the wiring script for live Codex configuration:

```bash
python3 scripts/codex-wiring.py --apply --live --workflow-owner omx
python3 scripts/codex-wiring.py --check --live --workflow-owner omx
```

`install.sh` installs symlinks and reports Codex wiring drift, but it does not apply live Codex TOML/hook changes. Start a fresh Codex process after applying hook/config changes; an already-running process may still be using the old configuration.

The Claude settings and machine overlay backups from this transition are in `~/.claude/`, named `*.pre-codex-wiring-20260907`. The local submodule had pre-existing changes which were preserved.

To return memory to hook-managed idle operation, first remove `AGMEM_NO_DAEMON=1` from the Claude machine overlay and corresponding live settings, then stop/disable the user service. Codex's fixed HTTP MCP additionally needs a ready daemon; disabling the service alone intentionally leaves that connection unavailable.

## Authentication check

An ordinary model response does not prove Apps health. Use a fresh app-server MCP status request to confirm `codex_apps` has a tool catalog. The 2026-09-07 check succeeded with 94 tools and no token error, without logout or a paid model call. A previous `401 token_expired` is not evidence of a current failure.

## Previous split-pane implementation ledger (historical)

The following results apply to the earlier implementation, not the fixed-row visual gate. New evidence is recorded under `.omo/evidence/codex-fixed-hud/`.

- Window-label stale-state regression: failed before fix, then 8 tests passed; isolated tmux showed the expected busy symbol and Codex profile color. Current pane was repaired through the normal label command.
- Claude statusline/cacheline: 4 + 8 regression tests passed unchanged.
- Memory wrapper: 5 executable-contract checks passed without importing agmem or touching stored memories.
- User service: `systemd-analyze --user verify` passed after symlink installation; live `/health` returned `ok: true`, namespace `main`.
- Live memory MCP: `initialize` HTTP 200 and `tools/list` returned seven tools; test MCP session closed after inspection, no tool writes performed.
- Memory repository regression suite: 1036 passed, 2 skipped.
- Native fresh probe: `agentic_memory` returned 7 tools, `codex_apps` returned 94 tools, and `toolsError` was null.
- Native hook trust: all 9 memory/window hooks were trusted and `enabled = true` using Codex `currentHash`.
- Codex live wiring: `python3 scripts/codex-wiring.py --apply --live --workflow-owner omx` was applied; the following `--check --live --workflow-owner omx` exited 0, confirming idempotence. Private backups were generated before changes.
- Main local verification bundle: 129 tests passed, covering wiring 14, HUD 16, window label 8, merge/status/cache/guard; basedpyright error-level gate reported 0 errors; `./install.sh --check` reported 24 normal checks.
- Actual companion HUD launch: pane `%3` was launched for parent `%2` and focus returned to the parent.
- Semantic live-config comparison against the private backup: unrelated sections unchanged; eight OMO workflow hooks disabled, existing OMX Stop enabled. Existing native footer choices were already correct and remained unchanged.
- Main re-ran isolated memory hook/HTTP tests after integration: 35 passed in 21.50 seconds; user service remains active with zero restarts.
- Fresh full memory suite: 1036 passed, 2 skipped, 3 capability warnings in 142.71 seconds. Missing optional Neo4j/LLM test capabilities are not live service failures.
- Explicit architect reviews passed for config/hook ownership and the final HUD logic. Scoped cleanup found no masking fallbacks and made no additional product changes.
- Ruff passed for new Python files with only the established hyphenated executable-name convention excluded (`N999`). CLI typecheck found no source errors. Strict checking of the two external memory test files is not clean (27 errors); this task does not claim a clean whole-repository typing gate. Runtime tests pass. Bash LSP was previously declined; shell syntax and runtime tests were used instead.

- Post-cleanup verification: 129 dotfiles tests and 35 isolated memory tests passed again; wrapper/launcher checks, typecheck, Ruff and diff whitespace checks passed.
- Final visual gate: two independent reviewers passed all 14 corrected PTY-to-browser captures (60/80/120 columns, ready/down, real live service, 80-to-60 resize). Watch uses exact three-row panes; one-shot CLI captures include a fourth row for its normal final newline. Source SHA-256: `47cb088816eb77b5b05e2ab720e44e140a236d0a52b001bd77f14debf35691ca`.

Historical screenshots, independent reviews and cleanup records are retained locally under `.omo/evidence/codex-wiring/`, excluded from the public repository to avoid publishing machine/session metadata.

At that earlier checkpoint, implementation and live integration were reported complete. The running conversation was not restarted; MCP tools/hooks were checked in separate fresh processes. This did not prove HUD availability in every next interactive process, as the later user report demonstrates. Authentication was not reset, and no synthetic test memories were written to the live store.

### Re-entry correction (2026-09-07)

The earlier restart instruction missed old parent shells: the observed bash started at 14:17, before the wrapper update at 20:10, and launched `codex resume` at 20:50 without a HUD pane. Native HUD lifecycle hooks recover on the first submitted turn even with the old wrapper; they do not guarantee pre-prompt display in an already-running old shell. Both hooks are appended without shifting existing memory/OMX entries; Codex-generated trust hashes are approved separately. The existing conversation's HUD was restored without restarting it.

Actual Codex 0.153.4 TUI verification used an isolated tmux server and CODEX_HOME with the real HOME. A closed localhost model endpoint prevented paid inference. Direct binary launch recovered the owned three-row HUD after a submitted turn, and exit removed it. Launch through the updated shell wrapper displayed the three-row HUD before any prompt. Initial no-prompt native-only tests correctly showed no HUD; those were not treated as passing startup evidence.

`bash scripts/test-codex-hud-lifecycle.sh` verifies real isolated tmux start/reuse/stop/re-entry, opt-out, outside-tmux behavior and refusal to kill a non-owned pane. It failed before the fix and passes afterward. The renderer is unchanged from the visual-reviewed SHA above.
