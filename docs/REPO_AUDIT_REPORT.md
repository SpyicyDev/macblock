# macblock — Repository Audit Report

Date: 2025-12-28
Commit (audited): bbce88c
Revision: third-pass maximum-effort audit + validation

## Scope
This report covers:
1. What the repo does (features/architecture)
2. Whether the current codebase appears to be in a properly working state
3. Code quality review (correctness risks, maintainability, security posture)
4. Documentation accuracy vs. current behavior

**Constraints:** No code changes were made. No privileged actions were executed.

## Methodology
- Third-pass validation (2025-12-28): re-ran checks, expanded searches, and re-validated every finding in this report
- Local verification via `just ci` (ruff format/lint, pyright, pytest, version check)
- CI-match verification via `uv run pytest --cov=macblock --cov-report=xml` (writes `coverage.xml`)
- Packaging sanity via `uv build` (writes `dist/`)
- CLI contract validation via `uv run macblock --help` + selected subcommand `--help` output
- Static review of key modules under `src/macblock/` (CLI, daemon, install/uninstall, DNS plumbing)
- Repo-wide pattern searches (broad exception handling, subprocess usage, unsafe APIs)
- Background subagent audits (explore), split by area:
  - Re-validate findings A–H
  - Documentation accuracy + gaps
  - CI/test alignment + quality gate coverage
  - Security/privilege posture
  - Packaging/release/dependency posture
- External reference check (librarian): confirm best practices for `sudo -E` and launchd hardening norms

## Fourth-pass remediation playbook (implementation steps)

**Goal:** Convert each finding/recommendation below into concrete, minimal, reviewable implementation steps.

**Provenance:** This playbook was expanded from parallel explore/librarian subagent drafts and then cross-checked against repo files for specific path/symbol/line citations.

**Scope/constraints (this playbook):**
- No privileged operations in tests (no `sudo`, no writes to `/Library` or `/var/db`, no `launchctl`).
- Prefer minimal diffs and repo-local patterns.
- Every checklist item cites evidence: a repo path + symbol name (and line numbers when available) and/or authoritative external docs (only where necessary).

### How to use this playbook
- Treat each Finding (A–K) as its own PR-sized unit unless explicitly grouped.
- Run the smallest relevant test subset first (file-level `pytest`), then `just ci` / `just check` before merging.
- When behavior changes, update CLI messaging to be unambiguous and add/adjust tests that capture the UX contract.

### A. `update` can report success without applying a blocklist

1) What to change
- `src/macblock/blocklists.py:update_blocklist` — the “small list” branch at `src/macblock/blocklists.py:232` currently warns but skips writing/compiling blocklist files (only compiles in the `else:` at `src/macblock/blocklists.py:235`) while still saving state (`src/macblock/blocklists.py:245`) and reloading dnsmasq (`src/macblock/blocklists.py:51`) and printing success (`src/macblock/blocklists.py:258`).

2) Why
- Current UX can claim “Blocklist updated” even when no new `blocklist.*` files were produced; users may think they’re protected while dnsmasq continues using the previous compiled rules.

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- [x] Decide the desired contract for “small” blocklists (threshold is currently hard-coded as `1000` at `src/macblock/blocklists.py:232`). Recommended default: **fail-fast** for `<1000` to avoid silently applying likely-bad downloads.
- [x] Option A (recommended): fail-fast (no state drift)
  - [x] In the compile spinner block, replace the warn-only path with an explicit failure:
    - [x] When `count_raw < 1000`, call `spinner.fail(...)` and raise `MacblockError` (import already present at `src/macblock/blocklists.py:20`).
    - [x] Include remediation in the error message: “If you intentionally use a small custom list, consider using a different source or add an override flag/config” (see optional enhancements below).
  - [x] Ensure the failure occurs **before** `save_state_atomic(...)` (`src/macblock/blocklists.py:245`) and before `reload_dnsmasq()` (`src/macblock/blocklists.py:53`).
  - [x] Guardrail: do not print `result_success(...)` (`src/macblock/blocklists.py:258`) on this path.
- Option B (alternative): apply-small (warn + still apply)
  - Move the `atomic_write_text(SYSTEM_RAW_BLOCKLIST_FILE, ...)` (`src/macblock/blocklists.py:235`) and `compile_blocklist(...)` call (`src/macblock/blocklists.py:236`) out of the `else:` so compilation happens for both large and small lists.
  - Keep a warning for `count_raw < 1000`, but ensure:
    - `count` reflects the compiled domain count (not the default `0` at `src/macblock/blocklists.py:229`).
    - The final message is unambiguous (e.g., include “(small list applied)” in the `result_success(...)` line at `src/macblock/blocklists.py:258`).
- Optional enhancement (defer if keeping diffs minimal): make the threshold configurable for custom URLs only (e.g., `--min-domains` flag) to support curated small lists without loosening safety for built-in sources.

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- [x] Extend `tests/test_blocklists.py` (currently only covers `compile_blocklist` at `tests/test_blocklists.py:6`).
- [x] Add unit tests for `update_blocklist` using `monkeypatch` (no network, no `/Library` writes):
  - [x] Monkeypatch `macblock.blocklists._download` (`src/macblock/blocklists.py:106`) to return controlled content.
  - [x] Monkeypatch `macblock.blocklists.atomic_write_text`, `macblock.blocklists.save_state_atomic`, and `macblock.blocklists.reload_dnsmasq` to record calls.
  - [x] Use `capsys` to assert messaging (e.g., `result_success(...)` output) is/ isn’t printed.
- [x] Suggested cases:
  - [x] Small list (<1000 domains) should **not** report success without applying:
    - [x] If Option A: assert `update_blocklist(...)` raises `MacblockError`; assert `save_state_atomic` and `reload_dnsmasq` not called.
    - If Option B: assert compilation/writes happen and success message indicates “small list applied”.
  - [x] HTML detection path: `_download` returns HTML-like prefix; assert `MacblockError` at `src/macblock/blocklists.py:224`; assert no writes/state/reload.
  - [x] SHA mismatch path: `_download(... expected_sha256=...)` raises `MacblockError` at `src/macblock/blocklists.py:133`; assert no writes/state/reload.

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- Option A may break users who intentionally use small custom lists; mitigate via an explicit override (flag/config) and clear error guidance.
- Option B increases risk of applying incomplete/malformed lists that slip past HTML detection (`src/macblock/blocklists.py:217`).
- Any change here is user-visible; treat as a behavior-contract change and document it.

6) Acceptance criteria (what “done” looks like)
- [x] `macblock update` never prints `Blocklist updated: 0 domains blocked` when compilation was skipped.
- [x] State updates, blocklist file writes, and dnsmasq reload either all occur together or none occur.
- [x] Added tests exercise the small-list branch and fail prior behavior.

### B. Subprocess wrapper may crash on non-UTF8 output

1) What to change
- `src/macblock/exec.py:run` — the `subprocess.run(..., text=True)` call at `src/macblock/exec.py:16` does not specify `encoding=` / `errors=`, which can raise `UnicodeDecodeError` if a subprocess emits undecodable bytes.
- Note: the timeout path already decodes bytes safely with `errors="replace"` at `src/macblock/exec.py:25` and `src/macblock/exec.py:30`.

2) Why
- Prevents hard crashes in CLI/daemon paths that call `run(...)` when a subprocess returns non-UTF8 output (robustness; “never crash on decode”).

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- [x] Modify the success-path `subprocess.run(...)` call in `src/macblock/exec.py:16` to include:
  - [x] `encoding="utf-8"`
  - [x] `errors="replace"`
- [x] Keep the `RunResult` API unchanged (`stdout`/`stderr` remain `str`).
- [x] Guardrail: avoid changing timeout behavior (it already returns `returncode=124` and appends a timeout suffix at `src/macblock/exec.py:35`).

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- [x] Add a focused unit test module (recommended: `tests/test_exec.py`) since `src/macblock/exec.py` currently has no direct tests (gap called out in `docs/REPO_AUDIT_REPORT.md:210`).
- [x] Use `unittest.mock.patch` or `monkeypatch` to avoid spawning real processes:
  - [x] Assert `subprocess.run` is invoked with `encoding="utf-8"` and `errors="replace"`.
  - [x] Simulate a `subprocess.TimeoutExpired` with `stdout`/`stderr` as bytes containing invalid UTF-8 and assert:
    - [x] `RunResult.returncode == 124`
    - [x] `stdout`/`stderr` contain the replacement character `�`
    - [x] `stderr` includes the timeout suffix from `src/macblock/exec.py:35`.

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- Behavior change: undecodable bytes are now represented as `�` instead of crashing. This can slightly affect log/diagnostic output but is strongly preferable.
- If any caller relies on a specific locale encoding, forcing UTF-8 may change rendered characters; mitigate by documenting that output is UTF-8 decoded with replacement.

6) Acceptance criteria (what “done” looks like)
- [x] `macblock.exec.run(...)` never raises `UnicodeDecodeError` due to subprocess output.
- [x] New unit tests cover both normal and timeout decode paths.

### C. Corrupt `state.json` can break CLI + daemon loops

1) What to change
- `src/macblock/state.py:load_state` — unguarded JSON parsing at `src/macblock/state.py:50` (`json.loads(path.read_text(...))`) will raise on invalid JSON or unreadable files.
- `src/macblock/state.py:load_state` — assumes `data` is a dict; a valid-but-wrong JSON type (e.g., `[]`) would break later `.get(...)` usage.
- `src/macblock/state.py:load_state` — `schema_version = int(...)` at `src/macblock/state.py:98` can raise `TypeError`/`ValueError` for unexpected types.
- Error type to use: `MacblockError` is the repo’s user-facing error (`src/macblock/errors.py:1`) and is printed cleanly by the CLI (`src/macblock/cli.py:58`).

2) Why
- A partially-written file, manual edits, or corruption can “brick” both unprivileged commands (e.g., `status`) and daemon reconciliation until repaired.

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- [x] Pick a stance. Recommended default: **fail-with-guidance** (do not silently reset), because state can contain critical DNS backup/managed-service data.
- [x] In `src/macblock/state.py:load_state`:
  - [x] Wrap `path.read_text(...)` and `json.loads(...)` (`src/macblock/state.py:50`) in `try/except`.
    - [x] Catch at least: `OSError`, `UnicodeDecodeError`, and `json.JSONDecodeError`.
    - [x] Raise `MacblockError` with actionable remediation (e.g., “state.json is corrupt; delete it to reset to defaults”).
  - [x] After parsing, validate `isinstance(data, dict)`; if not, raise `MacblockError` (“state.json must be an object”).
  - [x] Guard the `schema_version` coercion at `src/macblock/state.py:98`:
    - [x] If it cannot be coerced to an int, raise `MacblockError` with remediation.
    - [x] Keep the existing “schema mismatch” warning behavior (`src/macblock/state.py:100`) for valid ints that don’t match.
- [x] Ensure CLI behavior remains clean:
  - [x] No changes required for exit codes; `MacblockError` is already caught and printed as `error: ...` (`src/macblock/cli.py:58-60`).
- Call-site behavior expectations (interaction review):
  - `macblock status` loads state immediately (`src/macblock/status.py:76`). Decide whether to:
    - (A) let `MacblockError` propagate (clean `error: ...`, exit code 1), or
    - (B) catch `MacblockError` inside `src/macblock/status.py:show_status` and print a targeted `status_err("state.json", "corrupt")` plus remediation, then return `1`.
  - `macblock doctor` also loads state (`src/macblock/doctor.py:314`). Same choice as above; recommend (B) for doctor so it can still report other non-privileged signals (PID files, upstream.conf readability) even when state is corrupt.
  - `macblock daemon` loads state repeatedly (`src/macblock/daemon.py:605` and `src/macblock/daemon.py:641`). If `load_state` raises `MacblockError`, recommend exiting the daemon (Design A from Finding I) so launchd restart + logs make the failure visible instead of looping silently.

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- [x] Add a dedicated unit test module (recommended: `tests/test_state.py`) to test `load_state` directly with `tmp_path` (no `/Library` usage).
- [x] Suggested cases:
  - [x] Invalid JSON content: write `{ invalid` to a temp file; assert `load_state(...)` raises `MacblockError` and message contains “corrupt”/“invalid JSON”.
  - [x] Valid JSON but wrong top-level type (`[]` or `"str"`): assert `MacblockError`.
  - [x] Valid JSON with invalid `schema_version` type (e.g., `"two"`): assert `MacblockError`.
  - [x] Nonexistent file: assert current default return behavior still works (`src/macblock/state.py:39`).
- For daemon-level behavior, add/adjust tests in `tests/test_daemon.py` to simulate `load_state` raising `MacblockError` and assert the daemon either exits or surfaces a “failed” state (depending on the approach chosen in Finding I).

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- Fail-with-guidance is user-visible and can cause previously “working” commands to start erroring on corrupted state; this is intentional and safer than silently proceeding with unknown data.
- Reset-to-defaults would improve resilience but risks losing DNS backup data and causing unexpected DNS state changes; only use if you explicitly add clear warnings and/or backup rotation.

6) Acceptance criteria (what “done” looks like)
- [x] Corrupt `state.json` produces a clean `error: ...` with clear remediation steps (no tracebacks).
- [x] No command/daemon crashes from JSON/type errors.
- [x] Tests cover invalid JSON and wrong-type scenarios.

### D. `sudo -E` environment preservation is a security footgun

1) What to change
- `src/macblock/cli.py:_exec_sudo` — currently re-execs via `sudo -E` at `src/macblock/cli.py:115` and `src/macblock/cli.py:117`, passing the full current environment (`env = dict(os.environ)` at `src/macblock/cli.py:110`).
- Concrete privilege-boundary sensitivity in this repo: privileged install-time binary discovery consults env vars:
  - `MACBLOCK_DNSMASQ_BIN` at `src/macblock/install.py:102`
  - `MACBLOCK_BIN` at `src/macblock/install.py:123`

2) Why
- Preserving an arbitrary user environment across privilege escalation broadens the attack surface and can change privileged behavior via app-specific variables (even if OS strips some `LD_*` / `DYLD_*` vars).

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- [x] Recommended minimal-diff remediation: **remove `-E`** and avoid blanket env preservation.
  - In `src/macblock/cli.py:_exec_sudo` (`src/macblock/cli.py:102`):
    - [x] Keep setting `MACBLOCK_ELEVATED` in the parent env to prevent recursion checks (`src/macblock/cli.py:107-112`).
    - [x] Remove the `-E` flag from both execve invocations (`src/macblock/cli.py:115` and `src/macblock/cli.py:117`).
    - [x] Build a minimal env dict for `sudo` (e.g., `TERM`, `LANG`, `LC_*`, plus `MACBLOCK_ELEVATED`) instead of `dict(os.environ)`.
  - [x] Guardrail: explicitly drop `MACBLOCK_BIN` and `MACBLOCK_DNSMASQ_BIN` from the env passed into the escalation path to prevent them influencing privileged codepaths.
- Developer ergonomics mitigation (do not weaken default security):
  - `.envrc` sets `PYTHONPATH="$PWD/src"` for local dev (`.envrc:17`). Without preserve-env, elevated commands may run the installed package instead of the working tree.
  - Recommended: document a dev-only workflow that does not require `sudo -E` by default:
    - Prefer installing editable (so root picks up the same code), or
    - Provide a documented sudoers allowlist approach (`Defaults env_keep += "PYTHONPATH"`) for developers who understand the tradeoff.

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- [x] Add unit tests around `_exec_sudo` in `tests/test_cli.py` by monkeypatching:
  - `shutil.which` to return a fake sudo path and fake executable path.
  - `os.execve` to capture arguments instead of exec’ing.
- [x] Assert:
  - [x] No `-E` is present in the constructed argv.
  - [x] The env dict passed to `os.execve` does not include `MACBLOCK_BIN` / `MACBLOCK_DNSMASQ_BIN`.
  - [x] The env dict sets `MACBLOCK_ELEVATED=1`.
- [x] Guardrail test: if `MACBLOCK_ELEVATED=1` already, `_exec_sudo` raises `PrivilegeError` (`src/macblock/cli.py:107-109`).

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- Removing preserve-env can change which code is executed in dev setups (working tree vs installed version). Mitigate via docs and/or explicit developer configuration.
- If users rely on `MACBLOCK_BIN`/`MACBLOCK_DNSMASQ_BIN` in production, dropping these vars could change behavior; treat as a deliberate security hardening and document it.

6) Acceptance criteria (what “done” looks like)
- [x] Auto-elevation no longer uses blanket environment preservation.
- [x] Privileged codepaths cannot be influenced by `MACBLOCK_BIN` / `MACBLOCK_DNSMASQ_BIN` unless explicitly intended.
- [x] CLI tests validate argv/env construction for `_exec_sudo`.

External support
- `sudoers(5)` warns that `-E/--preserve-env` bypasses env restrictions and “only trusted users should be allowed to set variables in this manner”: https://www.sudo.ws/docs/man/sudoers.man/
- Apple launchd security guidance (ownership/permissions and declarative execution context): https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html

### E. Force uninstall is not fully best-effort

1) What to change
- `src/macblock/install.py:do_uninstall` — “Removing files” block uses direct `Path.unlink()` without `try/except` even when `--force` is set (`src/macblock/install.py:595` → e.g., `p.unlink()` at `src/macblock/install.py:604`, `src/macblock/install.py:612`, `src/macblock/install.py:622`, `src/macblock/install.py:651`). A single unlink failure aborts uninstall.

2) Why
- `uninstall --force` should be resilient: it should continue cleanup, accumulate failures, and report what could not be removed so users can finish manually.

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- [x] In `src/macblock/install.py:do_uninstall`:
  - [x] Introduce an accumulator (e.g., `file_leftovers: list[str] = []`) before the “Removing files” spinner.
  - [x] For each `if p.exists(): p.unlink()` site in that spinner (`src/macblock/install.py:596-652`):
    - [x] Wrap `p.unlink()` in `try/except OSError as e`.
    - [x] If `force` is true: append a descriptive entry to `file_leftovers` (include path + error) and continue; optionally `spinner.warn(...)` once per category.
    - [x] If `force` is false: call `spinner.fail(...)` and raise `MacblockError` to preserve current strictness.
  - Keep directory removals best-effort as currently implemented (they already `try/except` around `rmdir()` at `src/macblock/install.py:624-629` and `src/macblock/install.py:654-658`).
  - [x] Merge leftover reporting:
    - [x] At the end, the report currently only checks remaining launchd services (`leftovers` list at `src/macblock/install.py:668-678`). Extend the final message to include `file_leftovers` as well.

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- [x] Extend `tests/test_install.py` with a new test that exercises best-effort behavior:
  - [x] Use `tmp_path` to create fake plist/files and monkeypatch module-level path constants in `macblock.install` (this file already monkeypatches `install.SYSTEM_RESOLVER_DIR` at `tests/test_install.py:113`).
  - [x] Monkeypatch `Path.unlink` (or better: monkeypatch specific paths’ `.unlink` via small wrappers) to raise `OSError` for selected files.
  - [x] Call `do_uninstall(force=True)` and assert it returns `0` and does not raise.
  - [x] Call `do_uninstall(force=False)` with the same failures and assert it raises `MacblockError`.
  - [x] Capture output (via `capsys` or by intercepting `step_warn`) to assert a clear “Uninstall incomplete” message when leftovers remain.

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- In `--force` mode, uninstall will succeed more often but may leave files behind; this is expected and should be clearly reported.
- Be careful not to hide genuinely dangerous partial states: the final output must list exactly what remains.

6) Acceptance criteria (what “done” looks like)
- [x] `macblock uninstall --force` completes even if individual file deletions fail.
- [x] The final output lists leftover services and leftover files with enough detail to remediate manually.
- [x] Unit tests cover both force and non-force behavior.

### F. Allow/deny list management can be bricked by a single bad line

1) What to change
- `src/macblock/lists.py:_read_set` (`src/macblock/lists.py:16`) reads raw non-comment lines without validation.
- `src/macblock/lists.py:add_whitelist/remove_whitelist/list_whitelist` use set comprehensions that call `normalize_domain(...)` on every stored entry (e.g., `src/macblock/lists.py:49` and `src/macblock/lists.py:68`). A single invalid stored line causes `MacblockError` and breaks even `list`.
- `src/macblock/lists.py:_write_set` writes non-atomically via `Path.write_text(...)` (`src/macblock/lists.py:28-31`).
- Validation behavior source: `src/macblock/blocklists.py:normalize_domain` raises `MacblockError` on invalid domains (`src/macblock/blocklists.py:40-46`).
- Atomic write helper exists: `src/macblock/fs.py:atomic_write_text` (`src/macblock/fs.py:7-14`).

2) Why
- A user editing `whitelist.txt`/`blacklist.txt` manually (or a partial write) can permanently “brick” allow/deny commands until they hand-edit the files back into a valid state.
- Non-atomic writes risk truncated/empty files on crashes, which is exactly the scenario that makes later reads brittle.

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- [x] Make reads tolerant:
  - [x] Introduce a helper in `src/macblock/lists.py` (e.g., `_read_domains_tolerant(path: Path) -> set[str]`) that:
    - [x] Iterates `_read_set(path)` output or directly reads the file.
    - [x] For each line, calls `normalize_domain(line)` and catches `MacblockError`.
    - [x] On invalid line, prints a warning to stderr with the line number and a remediation hint (“remove/repair the line in whitelist.txt/blacklist.txt”).
    - [x] Continues processing remaining lines.
  - [x] Replace the brittle comprehensions in `add_*`, `remove_*`, and `list_*` (`src/macblock/lists.py:47-98`) with this tolerant helper.
- [x] Make writes atomic:
  - [x] Replace `_write_set` implementation (`src/macblock/lists.py:28-31`) with `atomic_write_text(path, content, mode=0o644)` from `src/macblock/fs.py:7`.
  - [x] Guardrail: ensure parent dir creation remains (`path.parent.mkdir(...)`) which `atomic_write_text` already handles (`src/macblock/fs.py:8`).
- [x] UX guardrails:
  - [x] `list_whitelist` / `list_blacklist` should still exit `0` even if invalid lines exist; warnings should be visible on stderr.
  - [x] `add_*` / `remove_*` should still function if the file contains unrelated invalid lines (skip+warn).
- [x] Interaction with compilation/reload (avoid re-bricking via `_recompile`):
  - [x] `src/macblock/lists.py:_recompile` invokes `compile_blocklist(...)` and will currently crash if the allow/deny files contain a bad line, because `src/macblock/blocklists.py:compile_blocklist` uses set comprehensions calling `normalize_domain(...)` on `_read_lines(...)` output (`src/macblock/blocklists.py:92-93`).
  - [x] Make compilation tolerant too: replace those comprehensions with a tolerant loop that catches `MacblockError` and skips invalid entries (with a warning that includes which file had the bad line). This keeps `allow add/remove` usable even when a user previously wrote a malformed line.

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- [x] Add a focused unit test module (recommended: `tests/test_lists.py`), since there are currently no list-file tests.
- [x] Use `tmp_path` and monkeypatch module-level constants in `macblock.lists`:
  - [x] Patch `SYSTEM_WHITELIST_FILE` / `SYSTEM_BLACKLIST_FILE` to point at `tmp_path` files.
  - [x] Patch `_recompile` to a no-op to avoid dependency on `SYSTEM_RAW_BLOCKLIST_FILE` (which would otherwise raise at `src/macblock/lists.py:35-36`).
- [x] Suggested cases:
  - [x] `list_whitelist` on a file containing valid + invalid domains prints valid domains and does not raise.
  - [x] `add_whitelist` with an existing invalid line still adds the requested domain and writes back a normalized/clean set.
  - [x] `_write_set` writes a trailing newline and does not partially truncate on simulated failure (unit test can at least assert writes go through `atomic_write_text`, by monkeypatching `macblock.lists.atomic_write_text`).
  - [x] Compilation tolerance: with an invalid line present in whitelist/blacklist, `_recompile` should not raise; it should compile using only valid entries and emit a warning pointing at the offending file.

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- Behavior change: previously, invalid stored lines caused hard failures; now they produce warnings and are ignored. This is almost always an improvement, but it can mask typos unless warnings are prominent.
- Decide whether to “auto-repair” files (rewrite without invalid lines) or only warn+skip. Auto-repair can surprise users; warn+skip is safer.

6) Acceptance criteria (what “done” looks like)
- [x] `macblock allow list` / `macblock deny list` never crash due to a single malformed line.
- [x] Writes to list files are atomic and permissions are consistent (`0o644`).
- [x] New unit tests cover invalid-line tolerance.

### G. IPv4-only "network ready" heuristic

1) What to change
- `src/macblock/daemon.py:_network_ready` currently requires an IPv4 address (`_get_interface_ipv4`) and otherwise reports `"no IPv4 for <iface>"` (`src/macblock/daemon.py:122-131`).
- IPv4 detection uses `/usr/sbin/ipconfig getifaddr <iface>` (`src/macblock/daemon.py:110-119`) and `_IPV4_RE` (`src/macblock/daemon.py:92`).
- Default route interface probing uses `/sbin/route -n get default` (`src/macblock/daemon.py:95-107`).
- Wait loop is `src/macblock/daemon.py:_wait_for_network_ready` (`src/macblock/daemon.py:134-190`) and logs readiness using the returned `ip` value.

2) Why
- On IPv6-only networks, the default route can exist but `ipconfig getifaddr` will never return a usable IPv4 address, causing repeated timeouts and noisy “applying anyway” behavior.

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- [x] Recommended minimal diff: treat network as “ready” when the default route interface has **either** IPv4 **or** IPv6.
- [x] In `src/macblock/daemon.py`:
  - [x] Add an IPv6 detector alongside `_get_interface_ipv4`:
    - [x] New regex (basic) for IPv6 strings (optionally including a zone id, e.g. `%en0`).
    - [x] New helper `_get_interface_ipv6(interface: str) -> str | None` that runs `/usr/sbin/ipconfig getv6ifaddr <iface>` with a short timeout, similar to `src/macblock/daemon.py:114`.
  - [x] Update `_network_ready` (`src/macblock/daemon.py:122`) to:
    - [x] Prefer IPv4 if available.
    - [x] Fall back to IPv6 if IPv4 is absent.
    - [x] Only report “not ready” if neither address is available.
  - [x] Guardrail: update the “reason” string so it is no longer IPv4-specific (e.g., change `"no IPv4 for ..."` at `src/macblock/daemon.py:129` to `"no IP for ..."`).

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- [x] Extend `tests/test_daemon.py` (already covers IPv4 readiness):
  - [x] Existing IPv4 readiness test is `test_wait_for_network_ready_waits_until_route_and_ip` (`tests/test_daemon.py:249-276`). Keep it to preserve current behavior.
  - [x] Add a new IPv6-only readiness test (recommended name: `test_wait_for_network_ready_ipv6_only`) that:
    - Reuses `_FakeClock` and patches `daemon.time.time/sleep` like existing tests (`tests/test_daemon.py:252-254`).
    - Monkeypatches `daemon.run` so:
      - `['/sbin/route','-n','get','default']` returns `interface: en0`.
      - `['/usr/sbin/ipconfig','getifaddr','en0']` always returns `returncode=1` (no IPv4).
      - `['/usr/sbin/ipconfig','getv6ifaddr','en0']` returns `returncode=0` and a valid IPv6 address.
    - [x] Asserts `daemon._wait_for_network_ready(15.0)` returns `True` without requiring `15s` of simulated time.
- Keep the existing timeout test `test_wait_for_network_ready_times_out` (`tests/test_daemon.py:278-293`) and update it only if the “reason” log message becomes less IPv4-specific.

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- This change makes the daemon apply earlier on IPv6-only networks; that’s intended.
- Separate consideration: dnsmasq is configured for `127.0.0.1` (IPv4 loopback). IPv6-only client DNS behavior may still not work; this finding is only about readiness gating, not the full IPv6 DNS story.

6) Acceptance criteria (what “done” looks like)
- [x] On IPv6-only networks, readiness checks succeed without waiting for IPv4.
- [x] Existing IPv4 readiness behavior remains unchanged.
- [x] Unit tests cover the IPv6-only path.

### H. Managed service selection is heuristic and may misclassify

1) What to change
- Primary: documentation + override guidance.
- Heuristic implementation: `src/macblock/system_dns.py:compute_managed_services` (`src/macblock/system_dns.py:163-200`). It excludes services based on name keywords (e.g., `vpn`, `tailscale`) and device prefixes (e.g., `utun`, `ppp`).
- Override mechanism exists: `dns.exclude_services` file at `src/macblock/constants.py:25` (`SYSTEM_DNS_EXCLUDE_SERVICES_FILE`). Parsing is in `src/macblock/system_dns.py:parse_exclude_services_file` (`src/macblock/system_dns.py:224-231`).
- Current test coverage exists but is limited: `tests/test_system_dns.py:24-41` checks that Tailscale is excluded and Wi‑Fi/Bridge are included.

2) Why
- The heuristic is intentional (avoid breaking VPN/split-DNS), but on unusual setups it can exclude services users expect to be managed (or include ones they don’t want touched). Without clear documentation, this looks like a bug.

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- Documentation changes (do not change behavior unless necessary):
  - In `README.md`:
    - Add a dedicated “Service classification and overrides” section near “How it works” that explains:
      - What kinds of services are typically included/excluded.
      - That exclusions are heuristic (name keywords + device prefixes).
      - How to override using `/Library/Application Support/macblock/dns.exclude_services`.
      - How to find exact service names (`/usr/sbin/networksetup -listallnetworkservices`).
      - File format: one service name per line; `#` comments allowed (matches parser at `src/macblock/system_dns.py:224-231`).
    - Include at least one example `dns.exclude_services` snippet.
  - In `docs/UNINSTALL.md`:
    - Mention that `dns.exclude_services` is among the files removed by uninstall (ties to footprint in README and expected cleanup).
- Optional (safe) code-only enhancement (keep behavior identical):
  - Add logging in `src/macblock/daemon.py:_apply_state` to print which enabled services are being excluded (per audit suggestion). This helps users debug misclassification without changing the heuristic. (Treat this as a separate PR to avoid mixing behavior/log changes with docs.)

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- Documentation-only changes: no tests required.
- If adding the optional logging or any heuristic tweaks:
  - Extend `tests/test_system_dns.py` to cover additional keywords/prefixes only if you change the heuristic.
  - Add a unit test for `parse_exclude_services_file` (`src/macblock/system_dns.py:224`) to confirm comment/blank-line handling.

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- Heuristic changes are risky (can break VPN configs); prefer documentation and explicit user overrides.
- Logging changes can be noisy but low-risk if rate-limited (daemon is long-running).

6) Acceptance criteria (what “done” looks like)
- README clearly explains the heuristic and `dns.exclude_services` usage with actionable steps.
- Users can correctly identify and exclude a service without reading source code.
- Existing tests for `compute_managed_services` remain green.

### I. Daemon failure handling can hide persistent breakage

1) What to change
- In `src/macblock/daemon.py:run_daemon`, failure counter logic currently resets after 5 failures and continues indefinitely:
  - Counter initialized at `src/macblock/daemon.py:596-597`.
  - On apply failure: increments at `src/macblock/daemon.py:619` and resets at `src/macblock/daemon.py:626`.
  - On exception: increments at `src/macblock/daemon.py:629` and resets at `src/macblock/daemon.py:636`.
  - Both paths log “too many consecutive failures … continuing anyway” (`src/macblock/daemon.py:623-635`).

2) Why
- launchd can report the daemon as “running” while it never successfully applies DNS state. Users may only notice by tailing logs; `status` will often show stale `Last apply` (`src/macblock/status.py:118-129`).

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- Provide two designs and choose one intentionally.

- [x] Design A (recommended): exit-after-N consecutive failures
- [x] Replace the “continuing anyway” reset behavior (`src/macblock/daemon.py:622-626` and `src/macblock/daemon.py:632-636`) with an exit path:
  - [x] Log an explicit message (keep `_log(...)` usage) indicating the daemon is exiting to let launchd restart.
  - [x] Exit with non-zero status (e.g., `return 1`) from `run_daemon`.
- Guardrails:
  - [x] Ensure the `finally` block runs to remove marker files (`src/macblock/daemon.py:672-675`). Returning from inside the `try` should still execute `finally`.
  - [x] Do not exit on a single transient failure; keep threshold (`max_consecutive_failures`) as the guard.

Design B (alternative): exponential backoff + persistent “failed” marker surfaced in status/doctor
- When `consecutive_failures >= max_consecutive_failures`, do not reset to 0 silently.
  - Instead, write a marker file (e.g., `VAR_DB_DIR/daemon.failure`) and begin exponential backoff (cap the sleep).
  - Clear the marker on the next successful apply.
- Surface to users:
  - `src/macblock/status.py:show_status` should detect the marker and report `status_err("daemon", "persistent failure since ...")`.
  - `src/macblock/doctor.py:run_diagnostics` should include an issue and a restart suggestion.

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- [x] For Design A (exit-after-N):
  - [x] Add a targeted unit test in `tests/test_daemon.py` that monkeypatches:
    - `daemon._apply_state` to always return `(False, ["issue"])`.
    - `daemon._wait_for_network_change_or_signal` to return immediately (e.g., `("timeout", 0)`) and avoid real subprocesses.
    - `daemon.load_state` to return a minimal `State` and `daemon._should_wait_for_network_before_apply` to `False`.
    - `daemon.VAR_DB_DAEMON_PID/READY/LAST_APPLY` to `tmp_path` to avoid `/var/db`.
  - [x] Assert `run_daemon()` returns `1` after `max_consecutive_failures` iterations.
- For Design B (marker/backoff):
  - Add unit tests that assert marker creation after threshold and removal after success, using patched marker path under `tmp_path`.
  - Add a `status`/`doctor` test that injects the marker and asserts messaging (requires capturing output).

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- Design A may cause crash loops if the failure is persistent, but that is often preferable to a silently-broken service.
- Design B keeps the daemon “running” but adds complexity and requires good UI surfacing; without that, it risks masking failures longer.

6) Acceptance criteria (what “done” looks like)
- [x] Persistent apply failures become visible without reading logs:
  - [x] Either via launchd restart behavior (Design A), or
  - Via explicit “failed” status in `macblock status` / `macblock doctor` (Design B, not implemented).
- [x] No more infinite “continuing anyway” loops after repeated failures.

### J. Daemon marker files are written non-atomically

1) What to change
- `src/macblock/daemon.py` writes marker files via `Path.write_text()`:
  - Last apply timestamp: `src/macblock/daemon.py:_write_last_apply_file` (`src/macblock/daemon.py:47-49`).
  - PID file: `src/macblock/daemon.py:_write_pid_file` (`src/macblock/daemon.py:540-543`).
  - Ready file: `src/macblock/daemon.py:_write_ready_file` (`src/macblock/daemon.py:545-548`).
- Status/doctor parse these files as integers and gracefully handle parse errors (`src/macblock/status.py:42-49`, `src/macblock/doctor.py:96-104`).
- Atomic write helper exists: `src/macblock/fs.py:atomic_write_text` (`src/macblock/fs.py:7-14`).

2) Why
- Marker files are consumed by `status` and by stale-daemon detection (`src/macblock/daemon.py:_check_stale_daemon` at `src/macblock/daemon.py:564-579`). Partial/truncated writes can create confusing “daemon running but markers unreadable” states.

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- [x] In `src/macblock/daemon.py`:
  - [x] Import `atomic_write_text` from `macblock.fs`.
  - [x] Replace each `write_text(...)` call in `_write_last_apply_file`, `_write_pid_file`, `_write_ready_file` with `atomic_write_text(path, text, mode=0o644)`.
  - [x] Guardrail: keep the trailing newline and parent directory creation. `atomic_write_text` already creates the parent dir (`src/macblock/fs.py:8`).

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- [x] Add unit tests to `tests/test_daemon.py`:
  - [x] Patch `daemon.VAR_DB_DAEMON_PID`, `daemon.VAR_DB_DAEMON_READY`, `daemon.VAR_DB_DAEMON_LAST_APPLY` to temp paths (pattern exists for other files at `tests/test_daemon.py:46-48`).
  - [x] Monkeypatch `daemon.atomic_write_text` to capture calls and assert `mode=0o644`.
  - [x] Assert written contents are parseable ints (PID/timestamps).

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- Very low risk; this is purely a robustness improvement.
- Slight behavior change: file permissions become consistent (`0o644`) instead of umask-dependent (ties into Finding K).

6) Acceptance criteria (what “done” looks like)
- [x] Marker files are written atomically and remain parseable.
- [x] `macblock status` and stale-daemon detection never break due to partially-written marker files.

### K. Some atomic writes do not pin file permissions

1) What to change
- `src/macblock/state.py:save_state_atomic` uses tmp+replace without setting mode (`src/macblock/state.py:142-146`).
- `src/macblock/daemon.py:_update_upstreams` writes `VAR_DB_UPSTREAM_CONF` via tmp+replace without setting mode (`src/macblock/daemon.py:281-285`).
- `src/macblock/control.py:_atomic_write` does tmp+replace and tries `chmod(0o644)` but suppresses errors (`src/macblock/control.py:84-92`).
- A consistent helper exists that pins mode: `src/macblock/fs.py:atomic_write_text` (`src/macblock/fs.py:7-14`).

2) Why
- tmp+replace without explicit `chmod` allows file permissions to drift based on process umask. These files are read by other components (`status`/`doctor`) and are part of the user-facing “filesystem footprint” contract.

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- [x] Establish a policy: generated config/state files should be written with `0o644` unless there is a specific reason to restrict further.
- [x] Update the known sites:
  - [x] `src/macblock/state.py:save_state_atomic`:
    - [x] After `tmp.replace(path)` (`src/macblock/state.py:146`), add `os.chmod(path, 0o644)` (import already exists in `src/macblock/fs.py`, but `state.py` currently does not import `os`).
    - [x] Alternatively, replace the tmp+replace block with `atomic_write_text(path, json_text, mode=0o644)`.
  - [x] `src/macblock/daemon.py:_update_upstreams`:
    - [x] Replace the manual tmp+replace at `src/macblock/daemon.py:281-285` with `atomic_write_text(VAR_DB_UPSTREAM_CONF, conf_text, mode=0o644)`.
  - [x] `src/macblock/control.py:_atomic_write`:
    - [x] Either replace implementation with `atomic_write_text(path, text, mode=0o644)`.
    - [x] Or keep the current approach but make `chmod` failures visible (do not silently ignore at `src/macblock/control.py:91-92`), because silent permission drift defeats the point of the fix.
- [x] Guardrail: ensure any callers that rely on reading these files without root remain able to do so (i.e., do not tighten to `0o600` unless you also adjust UX/docs).

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- [x] Add unit tests that run on temp directories (no system paths):
  - [x] `save_state_atomic`:
    - [x] Write state to `tmp_path` file, then assert `(path.stat().st_mode & 0o777) == 0o644`.
  - [x] `_update_upstreams`:
    - [x] Patch `daemon.VAR_DB_UPSTREAM_CONF` to a `tmp_path` file (pattern exists at `tests/test_daemon.py:46-48`).
    - [x] Call `_update_upstreams(...)` and assert file mode is `0o644`.
  - [x] `_atomic_write`:
    - [x] Call it with a `tmp_path` file and assert mode is `0o644` and errors are not silently suppressed in failure simulations.

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- Changing file permissions could affect users who intentionally rely on tighter permissions; however current behavior is already inconsistent due to umask. Pinning to `0o644` makes behavior predictable.
- If privacy is a concern, treat “tighten permissions” as a separate, explicit decision with documentation updates (see “Security posture improvements” below).

6) Acceptance criteria (what “done” looks like)
- [x] Files written via tmp+replace have predictable permissions (`0o644`) regardless of umask.
- [x] Tests validate the mode for the affected write sites.

### Docs: Documentation accuracy + completeness

Status: Completed (commit beec6b4).

1) What to change
- `README.md` has stale `macblock logs ... --stderr` references; current CLI flag is `--stream`:
  - CLI help defines `--stream <name>` for logs at `src/macblock/help.py:180-203`.
  - Parser implements `--stream` at `src/macblock/cli.py:163-183`.
- `README.md` does not document `macblock upstreams ...`, but the CLI supports it:
  - Help text at `src/macblock/help.py:436-455`.
  - Parser support at `src/macblock/cli.py:245-254`.
- `README.md` “Filesystem footprint” omits `upstream.fallbacks`:
  - Path constant is `src/macblock/constants.py:26` (`SYSTEM_UPSTREAM_FALLBACKS_FILE`).
- `README.md` should clarify `sources set` vs `update`:
  - `set_blocklist_source` only updates state (`src/macblock/blocklists.py:170-187`).
  - Install performs an initial update unless `--skip-update` (`src/macblock/install.py:488-501`).
- `README.md` mentions `dns.exclude_services` but does not explain format/usage:
  - File path constant at `src/macblock/constants.py:25`.
  - Parser accepts “one service name per line” with `#` comments (`src/macblock/system_dns.py:224-231`).
- `docs/UNINSTALL.md` should mention `_macblockd` cleanup semantics:
  - `_macblockd` is removed only in force uninstall (`src/macblock/install.py:662-666`).
- Security/UX doc note: install creates directories as world-readable (`0o755`) (`src/macblock/install.py:389-395` via `ensure_dir` in `src/macblock/fs.py:16-19`), which is a deliberate privacy/usability tradeoff.

2) Why
- Outdated flags and missing commands lead to user confusion, broken copy/paste instructions, and unnecessary support load.
- `dns.exclude_services` is the escape hatch for Finding H; without documented usage, heuristic misclassification looks like a bug.
- Directory permission expectations should be explicit given the threat model.

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- README.md updates (exact edits to make):
  - Replace all `--stderr` mentions with `--stream stderr`.
  - Add `upstreams` command under “Configuration” (use the examples from `src/macblock/help.py:450-455`).
  - Add `upstream.fallbacks` to the `/Library/Application Support/macblock/` file list.
  - Clarify `sources set` updates state only, and that `sudo macblock update` is required to download/compile/reload.
  - Add a short “Service classification and overrides” section (see Finding H) documenting `dns.exclude_services`:
    - One exact service name per line.
    - How to discover names: `/usr/sbin/networksetup -listallnetworkservices`.
    - Comments start with `#`.
- docs/UNINSTALL.md updates:
  - Add bullet under “What is removed…” stating `_macblockd` user/group is only removed by `sudo macblock uninstall --force`.
  - Add bullet listing `dns.exclude_services` among removed config files (ties to README footprint).
- SECURITY.md / README note (choose one place to keep concise):
  - Add a short statement that `/Library/Application Support/macblock` and `/Library/Logs/macblock` are created as `0o755` for usability (so non-root diagnostics can read logs), and that multi-user systems may want to tighten permissions.
- Doc QA guardrail (keep docs aligned with CLI truth):
  - Treat `src/macblock/help.py` (`MAIN_HELP` + `COMMAND_HELP[...]`) as the primary source of truth for flags/examples (e.g., logs flags at `src/macblock/help.py:180-203`, upstreams examples at `src/macblock/help.py:436-455`).
  - Cross-check parsing behavior in `src/macblock/cli.py:_parse_args` (e.g., logs flags at `src/macblock/cli.py:163-183`).
  - Ensure `tests/test_cli.py` continues to cover help-context extraction and parsing; if a doc bug regresses (like `--stderr`), consider adding a simple string-check test as a last resort.

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- Prefer doc-only changes without adding new tests.
- If you want an automated guardrail:
  - Add a doc test that asserts `README.md` does not contain `--stderr` (string search) and does contain `--stream stderr`. (This is optional and may be overkill for this repo.)

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- Documentation changes can lag behind behavior changes; consider adopting a lightweight policy: when changing CLI flags/help text, update README in the same PR.
- Tightening directory permissions would be a behavior change; document first before changing defaults.

6) Acceptance criteria (what “done” looks like)
- README examples match `macblock --help` / `macblock logs --help` output.
- README includes `upstreams` and `upstream.fallbacks`.
- README explains `dns.exclude_services` format and service name discovery.
- UNINSTALL describes `_macblockd` removal behavior.
- Privacy/usability tradeoff for directory modes is explicitly documented.

### CI/Release/Packaging hygiene

Status: Completed (commit fbee37d).

1) What to change
- PR/push CI (`.github/workflows/ci.yml`) does not run a packaging build (`uv build`). Current steps end after tests + CLI version check (`.github/workflows/ci.yml:40-50`).
- Lockfile policy is implicit:
  - CI uses `uv sync --dev` (`.github/workflows/ci.yml:28-29`) which can update resolution if lockfile is stale.
  - Release check uses the same (`.github/workflows/release.yml:23-24`).
  - The `just release` recipe uses `uv sync --dev --frozen` (`justfile:82-86`), implying lockfile should be authoritative for release.
- Dev dependencies are duplicated in two locations in `pyproject.toml`:
  - `[project.optional-dependencies].dev` (`pyproject.toml:36-42`) and `[dependency-groups].dev` (`pyproject.toml:44-50`).

2) Why
- Running `uv build` in PR CI catches packaging regressions earlier than tag-time (`uv build` currently only runs in `.github/workflows/release.yml:67-69`).
- CI should have a clear stance on whether `uv.lock` is authoritative; otherwise dependency drift can slip in unnoticed.
- Two sources of truth for dev deps can drift silently and break contributor workflows.

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- Add packaging sanity to PR CI:
  - In `.github/workflows/ci.yml`, add a step after tests (after `.github/workflows/ci.yml:40-41`) to run `uv build`.
  - Guardrail (time/cost): run `uv build` only once per matrix (e.g., only when `matrix.python-version == '3.12'`) to avoid redundant builds.
- Clarify lockfile policy (choose one):
  - Option A (recommended for CI): use `uv sync --locked --dev` so CI fails if `uv.lock` is out of date.
  - Option B (faster, less strict): use `uv sync --frozen --dev` to install exactly from `uv.lock` without validation.
  - Document the chosen stance in `CONTRIBUTING.md` (or in `AGENTS.md` if that’s the canonical contributor entrypoint).
- Align release checks (optional parity):
  - Consider making `.github/workflows/release.yml` “check” job match CI’s pytest invocation (coverage and `macblock --version`) if you want consistent signals.
  - Keep `uv build` in the release publish job as currently implemented (`.github/workflows/release.yml:67-69`).
- Dev dependency source-of-truth:
  - Decide whether `pyproject.toml` should keep both lists (pip extras + uv groups) intentionally.
  - If yes: add a short contributor note that they must be updated together, and consider a small CI check later.
  - If no: remove one and update documentation accordingly.

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- CI changes don’t require Python unit tests.
- Validation plan for CI changes:
  - Run `just ci` locally (already the repo’s CI-equivalent) and run `uv build` locally (`docs/REPO_AUDIT_REPORT.md:20`).
  - For workflow changes, use GitHub Actions dry-run in a PR and confirm:
    - `uv build` runs successfully.
    - Lockfile policy behaves as expected (CI fails if `pyproject.toml` and `uv.lock` drift).

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- Adding `uv build` increases CI time; mitigate by running it once per matrix.
- `--locked` is stricter and may require contributors to run `uv lock` more often; this is usually desirable for reproducibility.
- `--frozen` is faster but may allow drift if someone changes `pyproject.toml` without updating `uv.lock`.

6) Acceptance criteria (what “done” looks like)
- PR CI runs `uv build` and fails on packaging regressions.
- CI/release have an explicit lockfile policy (`--locked` or `--frozen`), documented for contributors.
- Dev dependency duplication is either documented as intentional or removed.

External support
- uv docs on lockfile sync flags (`--locked` vs `--frozen`): https://docs.astral.sh/uv/concepts/projects/sync/
- uv GitHub Actions integration guide (example uses `--locked`): https://docs.astral.sh/uv/guides/integration/github/#syncing-and-running

### Additional remediation items (non-lettered)

#### Low risk / maintainability nits

1) What to change
- Duplicate UI helpers existed in both `src/macblock/colors.py` and `src/macblock/ui.py`. (Completed: `src/macblock/colors.py` is now a compatibility re-export of `macblock.ui`.)
- `State.resolver_domains` was vestigial and has been removed. (Completed: older `state.json` keys are ignored on load.)
- Argument parsing is permissive:
  - Logs parser silently ignores unknown flags (`src/macblock/cli.py:169-184`).
  - Update parser silently ignores unknown flags (`src/macblock/cli.py:208-217`).
- HTML detection is heuristic:
  - `update_blocklist` inspects only the first 200 chars (`src/macblock/blocklists.py:217-224`).

2) Why
- Duplicated UI logic increases maintenance cost and makes it easier to introduce inconsistent output.
- Vestigial state fields create confusion and can mislead users editing `state.json`.
- Permissive parsing hides typos and can lead to “command didn’t do what I expected” support issues.
- Weak HTML detection can allow error pages to progress into the “small list” behavior (Finding A).

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- Duplicate UI helpers:
  - Decide which module is canonical. Recommended: keep `src/macblock/ui.py` as the canonical UI API (it already hosts Spinner and status helpers).
  - Make `src/macblock/colors.py` a thin compatibility wrapper that re-exports from `macblock.ui`, then optionally migrate imports to `macblock.ui` in a later PR.
- Vestigial `resolver_domains`:
  - Either (A) remove the field from `State` and its parsing, or (B) make it consistently persisted if it is intended.
  - Guardrail: because it is currently read but not persisted, removing it is likely non-breaking; if you remove it, ensure `load_state` ignores unknown keys to preserve backward compatibility.
- Strict arg parsing:
  - For `logs` and `update`, treat unknown flags as `MacblockError` with a hint to run `macblock <cmd> --help`.
  - Guardrail: this is a behavior change; document it and add tests.
- Improve HTML detection (optional, ties to Finding A):
  - Consider using HTTP response headers (Content-Type) in `_download` (`src/macblock/blocklists.py:106-135`) and/or expand the heuristic beyond 200 chars.

4) Tests (exact tests to add/adjust, what to assert, how to simulate without privilege)
- UI helper consolidation: existing tests should remain green; add targeted import smoke tests only if needed.
- `resolver_domains`: add a `tests/test_state.py` case asserting old state.json with `resolver_domains` loads without crashing, and that the field is either ignored or consistently persisted based on chosen approach.
- Strict parsing: add `tests/test_cli.py` cases asserting unknown flags raise `MacblockError`.
- HTML detection: add `tests/test_blocklists.py` cases with varied HTML-like content.

5) Risks & tradeoffs (compatibility, behavior change, rollout concerns)
- UI consolidation is low risk but is a refactor; keep it separate from functional fixes.
- Removing `resolver_domains` could break external tooling that reads state.json; mitigate by leaving key ignored rather than crashing.
- Strict parsing can break scripts that relied on ignored flags.

6) Acceptance criteria (what “done” looks like)
- No duplicate UI implementations remain without a deliberate compatibility plan.
- State schema no longer contains confusing, non-persisted fields.
- Unknown CLI flags fail fast with actionable help.

#### Broad exception handling inventory

1) What to change
- Repo-wide `except Exception` usage exists across multiple files (inventory in this report; representative sites include `src/macblock/status.py:48`, `src/macblock/daemon.py:628`, `src/macblock/install.py:244`).

2) Why
- Broad catches are sometimes correct (best-effort cleanup, diagnostic probes), but in user-facing flows they can hide actionable context and make failures harder to debug.

3) Implementation steps (ordered checklist, minimal diffs, guardrails)
- Categorize each `except Exception` site into:
  - “best-effort cleanup / diagnostics” (keep broad catch but add context logging), vs
  - “user-facing correctness” (tighten to specific exceptions and/or raise `MacblockError` with remediation).
- Apply changes one file at a time (recommended order): `src/macblock/daemon.py`, then `src/macblock/install.py`, then `src/macblock/blocklists.py`.
- Guardrail: do not change behavior in diagnostic-only sites unless you also update tests.

4) Tests
- Add targeted tests that inject failures via monkeypatch and assert:
  - user-facing commands return `MacblockError` with clear messaging, and
  - diagnostic commands continue to function (return defaults) where intended.

5) Risks & tradeoffs
- Tightening exception types can surface new errors that were previously hidden; this is desirable but must be paired with clear UX.

6) Acceptance criteria
- Broad catches remain only where best-effort behavior is explicitly intended.
- User-facing failures show actionable errors.

#### External sanity-check improvements (optional)

1) What to change
- DNS cache flushing after DNS changes: add best-effort cache flush after state application in `src/macblock/daemon.py` (DNS changes occur via `set_dns_servers` in `_enable_blocking` at `src/macblock/daemon.py:324-329` and restore in `_disable_blocking` at `src/macblock/daemon.py:358-365`).
- Port-53 blocker messaging: enhance `src/macblock/install.py:_run_preflight_checks` conflict message (currently at `src/macblock/install.py:276-94`) when the blocker is likely Homebrew-managed dnsmasq.
- `.local` caveats: document that `.local` uses multicast DNS and is not blocked by unicast DNS rules.

2) Why
- Cache flushing reduces “stale DNS” confusion after enabling/disabling.
- Better conflict messaging reduces install friction for Homebrew users.
- `.local` docs set correct expectations.

3) Implementation steps
- Cache flush (best-effort): run `dscacheutil -flushcache` and `killall -HUP mDNSResponder` after successful apply, ignoring failures.
- Port blocker messaging: when `blocker` contains `dnsmasq` (`src/macblock/install.py:80-94`), suggest `brew services stop dnsmasq` / `brew uninstall dnsmasq` if appropriate.
- Docs: add a short troubleshooting note referencing `.local`/Bonjour.

4) Tests
- Cache flush: monkeypatch `run` to assert the intended commands are invoked.
- Port blocker messaging: extend `tests/test_install.py` to assert the error message includes Homebrew guidance when blocker is `dnsmasq`.
- `.local` docs: doc-only change.

5) Risks & tradeoffs
- Cache flush is a privileged operation; ensure it is best-effort and doesn’t fail the daemon.
- Homebrew detection can be heuristic; keep messaging careful.

6) Acceptance criteria
- Users see fewer “it didn’t apply” reports after toggling.
- Install error messages provide clear next steps.
- Docs clarify `.local` behavior.

External support
- `dscacheutil(1)` and `mDNSResponder(8)` man pages on macOS.
- RFC 6762 (mDNS; `.local` special-use domain): https://datatracker.ietf.org/doc/html/rfc6762

#### CI extras (Dependabot, Ruff configuration)

1) What to change
- Dependabot is not currently configured (no `.github/dependabot.yml` / `.github/dependabot.yaml` found).
- Ruff is used in CI (`.github/workflows/ci.yml:31-35`) but there is no explicit `[tool.ruff]` configuration in `pyproject.toml` (`pyproject.toml:52-69`), so only defaults apply.

2) Why
- Dependabot reduces dependency drift and keeps dev tooling current.
- Explicit ruff configuration makes lint expectations stable and allows enabling targeted rule families.

3) Implementation steps
- Add `.github/dependabot.yml` to check Python dependencies (pyproject) on a weekly cadence.
- Add `[tool.ruff]` config to `pyproject.toml` to enable additional rule families incrementally (start with low-noise rules) and explicitly select/ignore as desired.

4) Tests
- Validate in CI by opening a PR:
  - CI passes with new ruff config.
  - Dependabot creates PRs (may take time after merge).

5) Risks & tradeoffs
- Enabling additional ruff rules can cause large diffs; roll out gradually and avoid mixing with functional changes.

6) Acceptance criteria
- Dependabot is present and active.
- Ruff config is explicit and CI remains green.

### Suggested PR breakdown (by risk/area)
- PR1 (low risk, high reliability): Finding B (`src/macblock/exec.py` decoding) + Finding J (daemon marker atomic writes) + Finding K (pin modes for tmp+replace writers).
- PR2 (user-visible correctness): Finding A (update false success) + README/UNINSTALL doc fixes (flags, upstreams docs, sources set vs update).
- PR3 (resilience to local corruption): Finding C (state.json corruption handling) + Finding F (tolerant allow/deny parsing + atomic writes).
- PR4 (privileged safety hardening): Finding D (`sudo -E` removal/allowlist) + any related doc updates.
- PR5 (daemon behavior/edge networks): Finding G (IPv6 readiness) + Finding I (failure handling strategy) + optional Finding H logging surfacing.

Guardrails for all PRs:
- Keep each PR narrowly scoped; avoid refactors.
- Add or update tests in the same PR for behavior changes.
- Run `just check` (or at minimum `just ci` + targeted pytest) before merge.

---

## 1) Repository Overview (What it does)

### High-level
`macblock` is a macOS-only Python CLI + daemon that runs a local `dnsmasq` instance on `127.0.0.1:53` and redirects DNS for selected macOS network services to localhost while preserving split-DNS behavior (VPN/corporate domain-specific resolvers).

### Primary user features
- DNS-level blocking using `dnsmasq` with compiled `server=/domain/` rules
- Enable/disable blocking, plus pause/resume with a timer
- Blocklist source selection and update (StevenBlack / HaGeZi / OISD or custom URL)
- Allow/deny list management (whitelist/blacklist)
- Diagnostics:
  - `status` (service state, upstreams)
  - `doctor` (health checks, port conflicts, config existence, warning on encrypted DNS)
  - `logs` (tails/streams log files)
  - `test` (runs `dig` against localhost dnsmasq and interprets results)

### Key architectural components
- CLI entrypoint: `src/macblock/cli.py` (custom parser + dispatch, plus auto-elevation)
- Daemon reconcile loop: `src/macblock/daemon.py`
  - Watches network changes via `notifyutil` and periodically reconciles state
  - Reads/writes state at `/Library/Application Support/macblock/state.json`
  - Computes “managed services” via `src/macblock/system_dns.py`
  - Writes dynamic upstream config to `/var/db/macblock/upstream.conf`
- Installation/uninstallation: `src/macblock/install.py`
  - Creates LaunchDaemons (`com.local.macblock.daemon`, `com.local.macblock.dnsmasq`)
  - Creates system user `_macblockd` for dnsmasq to drop privileges (`src/macblock/users.py`)
- Subprocess wrapper: `src/macblock/exec.py`

### Paths & persistence
Paths are centralized in `src/macblock/constants.py`.
- Persistent config/state: `/Library/Application Support/macblock/`
- Runtime: `/var/db/macblock/`
- Logs: `/Library/Logs/macblock/`
- LaunchDaemons: `/Library/LaunchDaemons/`

---

## 2) Working State Verification

### CI / quality gate status
Local run of checks succeeded:
- `uv run ruff format --check src/macblock tests`: PASS
- `uv run ruff check src/macblock tests`: PASS
- `uv run pyright src/macblock`: PASS
- `uv run pytest`: PASS (39 tests)
- `uv run pytest --cov=macblock --cov-report=xml`: PASS (`coverage.xml` produced)
- `uv run macblock --version`: PASS (0.2.8)
- `uv build`: PASS (sdist + wheel)

This matches the intent of `.github/workflows/ci.yml` (including coverage) and validates the release build backend locally.

### What was not run (by design)
- Any real install/enable/uninstall flows (these are privileged and would mutate system DNS and launchd state).

### Conclusion (working-state)
Within the limits of non-privileged verification:
- The repo is in a “clean” state: formatting, lint, types, and tests are green.
- CLI parsing/help output is consistent and functional.

However, several correctness/robustness issues were identified that could affect real-world behavior (see Findings).

---

## 3) Code Quality & Correctness Findings

### High risk (should be addressed)

**Validation:** Third-pass check against `bbce88c`.

**Third-pass claim validation (A–H):**
- A — Confirmed (`src/macblock/blocklists.py:190`): fit fix is to either fail fast or still apply small lists, but do not update state/reload/print success when compilation is skipped.
- B — Confirmed (`src/macblock/exec.py:14`): fit fix is to set an explicit `encoding=` + `errors=` for `subprocess.run(..., text=True)`.
- C — Confirmed (`src/macblock/state.py:38`): fit fix is to catch `JSONDecodeError`/type coercion failures and surface a `MacblockError` with remediation (or reset to defaults).
- D — Confirmed (`src/macblock/cli.py:102`): fit fix is to remove `sudo -E` or replace it with a tight allowlist of variables; keep in mind dev workflows that rely on `PYTHONPATH`.
- E — Confirmed (`src/macblock/install.py:50`): fit fix is to make `--force` fully best-effort by catching/unlinking errors and reporting leftovers at the end.
- F — Confirmed (`src/macblock/lists.py:16`): fit fix is tolerant parsing (skip invalid lines with warnings) + atomic writes; also ensure update/compile paths don’t crash on a single bad list entry.
- G — Confirmed (`src/macblock/daemon.py:134`): fit fix is to consider IPv6-only networks in the readiness check (or reduce reliance on IPv4 address probing).
- H — Confirmed (`src/macblock/system_dns.py:163`): fit fix is primarily documentation + clearer override guidance (`dns.exclude_services`) to avoid surprising misclassification.

#### A. `update` can report success without applying a blocklist
- Location: `src/macblock/blocklists.py` (`update_blocklist`)
- Behavior: if the downloaded list parses to fewer than 1000 domains, it warns and *does not write/compile* `blocklist.raw` / `blocklist.conf`, yet still updates state, reloads dnsmasq, and prints a success message with `0` domains.
- Impact: users can think the update worked when it didn’t apply anything; state may reflect a new source while dnsmasq continues using the previous compiled blocklist.
- Recommendation: make this branch explicit and unambiguous:
  - either fail with a non-zero exit + actionable error,
  - or still write/compile (with warning),
  - or warn loudly and return non-zero (“not applied”).
- Note: if keeping a “minimum domains” threshold, avoid reloading dnsmasq and avoid printing success when compilation was skipped; consider making the threshold configurable or source-specific.

#### B. Subprocess wrapper may crash on non-UTF8 output
- Location: `src/macblock/exec.py` (`run`)
- Behavior: uses `subprocess.run(..., text=True)` without setting `encoding=` / `errors=`. If a command emits undecodable bytes, `UnicodeDecodeError` can be thrown.
- Impact: CLI/daemon can crash on unexpected subprocess output, leading to repeated reconcile failures.
- Recommendation: use explicit decoding (e.g. `encoding='utf-8', errors='replace'`) to guarantee a `RunResult` is returned.

#### C. Corrupt `state.json` can break CLI + daemon loops
- Location: `src/macblock/state.py` (`load_state`)
- Behavior: `json.loads(path.read_text(...))` and subsequent type coercions (e.g., `schema_version = int(...)`) are not wrapped; invalid JSON or unexpected types will raise and propagate.
- Impact: a partially-written file, manual edits, or IO corruption can “brick” normal operation until repaired.
- Recommendation: catch `JSONDecodeError` and raise a `MacblockError` with remediation (or fall back to defaults with a warning, depending on desired stance).

#### D. `sudo -E` environment preservation is a security footgun
- Location: `src/macblock/cli.py` (`_exec_sudo`)
- Behavior: re-execs via `sudo -E`, explicitly preserving environment variables.
- Impact: root can inherit a manipulated environment (`PYTHONPATH`, `PATH`, etc.). Even if the local user is the attacker, this materially worsens the security posture.
- Third-pass nuance: `SECURITY.md` assumes a trusted single-user admin machine; under that model this is primarily hardening/self-footgun. On multi-user systems it becomes a more concrete privilege-boundary risk.
- Note: this is particularly concrete here because install-time code honors `MACBLOCK_BIN` and `MACBLOCK_DNSMASQ_BIN` from the environment to locate executables; with `sudo -E` those values can cross the privilege boundary.
- Recommendation: avoid `-E` or preserve only an allowlist of safe variables; document the tradeoff.
- External rationale: `sudoers(5)` (sudo.ws) documents `-E/--preserve-env` and `SETENV` and explicitly warns that “only trusted users should be allowed to set variables in this manner”; prefer a minimal/allowlisted environment across escalation (note: OS-level stripping of `LD_*`/`DYLD_*` does not address app-specific vars like `MACBLOCK_BIN`).

### Medium risk (robustness / UX)

#### E. Force uninstall is not fully best-effort
- Location: `src/macblock/install.py` (`do_uninstall`)
- Observation: while many cleanup steps are best-effort, the “Removing files” section calls `Path.unlink()` directly for multiple paths without `try/except` and without honoring `--force` semantics; a single permission issue or race can abort uninstall even in `--force` mode.
- Impact: users can get stuck in partial states.
- Recommendation: treat `--force` as “accumulate errors and continue”; report leftovers at end.

#### F. Allow/deny list management can be bricked by a single bad line
- Location: `src/macblock/lists.py`
- Behavior: `_read_set` accepts any non-empty non-comment line; then `list_*`/`add_*`/`remove_*` use set comprehensions like `{normalize_domain(x) for x in _read_set(...)}` that will raise on the first invalid entry (bricking even `list`). Writes via `_write_set` use non-atomic `Path.write_text()`.
- Impact: user must manually repair files before commands work.
- Recommendation: atomic write and tolerant reads (skip invalid lines with warnings).

#### G. IPv4-only “network ready” heuristic
- Location: `src/macblock/daemon.py` (`_wait_for_network_ready`)
- Behavior: relies on IPv4 (`ipconfig getifaddr`, IPv4 regex).
- Impact: on IPv6-only networks, daemon may regularly time out and “apply anyway”.
- Recommendation: consider IPv6 readiness or skip readiness gating when IPv6-only.

#### H. Managed service selection is heuristic and may misclassify
- Location: `src/macblock/system_dns.py` (`compute_managed_services`)
- Behavior: excludes/chooses services based on name substrings and device prefixes.
- Impact: potential false positive/false negative on unusual setups.
- Recommendation: document the heuristic and provide user override guidance (via `dns.exclude_services`) more clearly.

#### I. Daemon failure handling can hide persistent breakage
- Location: `src/macblock/daemon.py:582`
- Behavior: after repeated failures in `_apply_state`, the loop logs an error but resets the counter after 5 failures and continues indefinitely (`src/macblock/daemon.py:609`).
- Impact: launchd can report the job as “running” while DNS state never successfully applies; users may only notice via logs.
- Recommendation: either exit after N consecutive failures (let launchd restart and surface failure) or add exponential backoff + a “failed” marker surfaced in `status`/`doctor`.

#### J. Daemon marker files are written non-atomically
- Location: `src/macblock/daemon.py:47`, `src/macblock/daemon.py:540`, `src/macblock/daemon.py:545`
- Behavior: PID/ready/last-apply marker files use `Path.write_text()` directly.
- Impact: partial writes or truncation can break `status`/`doctor` parsing and stale-daemon detection.
- Recommendation: switch these to `atomic_write_text(..., mode=0o644)` (same pattern used for other config files).

#### K. Some atomic writes do not pin file permissions
- Location: `src/macblock/state.py:130`, `src/macblock/daemon.py:255`
- Behavior: `save_state_atomic()` and `_update_upstreams()` use tmp+replace without explicitly setting mode.
- Impact: resulting file permissions can drift based on umask (and may diverge from docs/expectations).
- Recommendation: explicitly `chmod` after replace (or route through `atomic_write_text`).

### Low risk / maintainability nits
- Duplicate color/printing helpers exist in both `src/macblock/colors.py` and `src/macblock/ui.py`.
- `State.resolver_domains` appears vestigial/confusing:
  - It is present in the dataclass and initial install seeding, but is not persisted by `save_state_atomic` and is overwritten to `[]` by `replace_state`.
- Argument parsing is permissive: unknown flags are ignored in several commands (typos can silently fall back to defaults).
- Blocklist download “HTML detection” is heuristic (first ~200 characters); some error pages may slip through and then interact with the “small list” behavior in Finding A.

### Broad exception handling inventory
Found ~50 `except Exception` sites across 10 files (mostly `install.py`, `daemon.py`, `doctor.py`, `status.py`). Some are appropriate (best-effort cleanup and diagnostic probes), but several suppress actionable context that would help users debug real-world failures.

---

## 4) Test Suite Assessment

### What’s covered well
- CLI parsing for all commands: `tests/test_cli.py`
- Daemon reconcile behaviors and timing: `tests/test_daemon.py` (heavy monkeypatching)
- Blocklist compilation basics: `tests/test_blocklists.py`
- Resolver parsing and upstream selection: `tests/test_resolvers.py`
- System DNS parsing and managed service computation: `tests/test_system_dns.py`

### Notable gaps
- `src/macblock/exec.py`: no tests for decoding edge cases or error behavior.
- `src/macblock/state.py`: no tests for corrupt JSON / schema mismatches beyond warnings.
- `src/macblock/blocklists.py`: no tests for the “small list” branch, HTML detection, size cap, SHA mismatch.
- Privileged flows (install/uninstall/launchctl/dscl) are understandably not integration-tested.

### Brittleness risks
- Several daemon tests validate internal helper behavior via monkeypatching private functions; this is fine for a small project, but it can make refactors disproportionately expensive.

---

## 5) Documentation Accuracy Review

### Confirmed doc bugs
- `README.md` documents `macblock logs ... --stderr`, but the CLI no longer has `--stderr`. Current flag is `--stream stderr` (verified by `src/macblock/cli.py`, `src/macblock/help.py`, and `tests/test_cli.py`).
- `README.md` troubleshooting also references `--stderr` (examples should use `--stream stderr`).

### Missing or incomplete docs
- `README.md` doesn’t document the `upstreams` command (`macblock upstreams list|set|reset`), but it exists and is shown in CLI help.
- `README.md` “Filesystem footprint” does not list `upstream.fallbacks` (the fallback configuration file at `/Library/Application Support/macblock/upstream.fallbacks`).
- `docs/UNINSTALL.md` does not mention that the `_macblockd` system user/group is only removed in `uninstall --force` (`src/macblock/install.py:662`, `src/macblock/users.py:71`).
- `README.md` should clarify that `sources set` updates state only; users must run `sudo macblock update` to actually download/compile/reload.
- `README.md` lists `dns.exclude_services` but doesn’t explain how to use it (exact service names, one per line).

### Third-pass validation notes (docs)
- Confirmed: `macblock logs` uses `--stream auto|stdout|stderr`, not `--stderr` (verified via `uv run macblock logs --help`).
- Confirmed: `macblock upstreams` exists and uses `/Library/Application Support/macblock/upstream.fallbacks` (`src/macblock/constants.py:26`).
- Needs nuance: `macblock sources set` only changes `state.json` (`src/macblock/blocklists.py:170`); `install` will also run `update` unless `--skip-update` (`src/macblock/install.py:488`).

---

## 6) External Sanity-Check (macOS DNS + launchd patterns)

A lightweight external sanity-check suggests the overall approach is aligned with common macOS patterns:
- Uses `networksetup` for per-service DNS changes (instead of editing SIP-sensitive files)
- Uses `scutil --dns` to preserve split DNS
- Uses modern `launchctl bootstrap system` / `bootout` patterns
- Uses `dnsmasq` bound to loopback and drops privileges via a dedicated user

Potential improvements (not necessarily bugs):
- Consider flushing DNS caches after applying DNS changes (advisory; can reduce “stale DNS” confusion)
- Port conflicts are already checked during install (bind + `lsof`); consider making the “what is blocking :53” messaging more explicit when the blocker is a Homebrew-managed service
- Document `.local` caveats (Bonjour/mDNS interactions)

---

## 7) Packaging, Dependencies & Release Engineering (Coverage Gap)

### Findings
- Build backend is setuptools (`pyproject.toml`), while `uv` is used as the runner/builder frontend (this is a valid pairing).
- Main CI (`.github/workflows/ci.yml`) does not run `uv build`, so packaging regressions may not be caught until tag-time (third-pass local `uv build` succeeded).
- Release workflow (`.github/workflows/release.yml`) does run `uv build` (on Ubuntu) and validates that the tag version matches the package version. Note: the release "check" job does not run coverage or `macblock --version` like `.github/workflows/ci.yml` does (optional parity improvement). This is fine for a pure-Python package; if you ever ship platform-specific wheels, consider building on macOS.
- Dev dependencies are declared twice (`[project.optional-dependencies].dev` and `[dependency-groups].dev`). This may be intentional (pip extras vs. `uv` dependency groups), but it creates a “two sources of truth” risk unless explicitly documented/kept in sync.
- `uv.lock` is committed (good for reproducibility), but there is no explicit policy for when/how to update it.
- CI uses `uv sync --dev` without `--frozen`; if the lockfile is intended to be authoritative, consider using `--frozen` in CI/release checks to prevent accidental drift.

### Recommendations
- Consider adding `uv build` to the PR/push CI job as a lightweight packaging sanity check.
- Clarify (in contributor docs) whether dev deps should live in optional-dependencies, dependency-groups, or both.

## 8) CI / Quality Coverage Gaps (Coverage Gap)

- CI covers formatting/lint/types/tests well, but does not include packaging build checks on PR/push or a Dependabot configuration. Dependency vulnerability scanning (e.g., pip-audit/safety) is possible, but ROI is limited here because runtime dependencies are currently empty.
- Ruff runs its default rule set (no `[tool.ruff]` config); if you want stricter quality/security checks, consider enabling additional rule families.
- Repo-wide scans found no TODO/FIXME/XXX markers in `src/` or `tests/`, and no `shell=True` usage.

## Recommendations (Prioritized)

### Top 6 (highest ROI)
1. Harden subprocess decoding in `src/macblock/exec.py` (avoid unexpected `UnicodeDecodeError`).
2. Make `update_blocklist` “small blocklist” behavior explicit and correct (avoid false success).
3. Handle corrupt `state.json` gracefully with actionable user guidance.
4. Improve uninstall robustness in `--force` mode (best-effort removal + clear leftover reporting).
5. Harden allow/deny list file handling (atomic writes + tolerant parsing).
6. Improve daemon failure handling + marker-file atomicity (avoid “running but broken” loops).

### Security posture improvements
- Revisit `sudo -E` usage and environment preservation (see Finding D).
- Decide/document the intended privacy tradeoff for `/Library/Logs/macblock` and `state.json` readability (install creates directories as `0o755`).

### Documentation updates
- Fix `--stderr` references; document `upstreams`; add `upstream.fallbacks` to filesystem footprint; clarify `sources set` vs `update`; explain `dns.exclude_services` usage; mention `_macblockd` removal semantics.

---

## Appendix: Notable files
- CLI: `src/macblock/cli.py`, `src/macblock/help.py`
- Daemon: `src/macblock/daemon.py`
- Install/uninstall: `src/macblock/install.py`, `src/macblock/launchd.py`, `src/macblock/users.py`
- DNS config: `src/macblock/system_dns.py`, `src/macblock/resolvers.py`, `src/macblock/dnsmasq.py`
- Blocklists: `src/macblock/blocklists.py`, `src/macblock/lists.py`
- Diagnostics: `src/macblock/status.py`, `src/macblock/doctor.py`, `src/macblock/logs.py`
- Docs: `README.md`, `docs/UNINSTALL.md`, `docs/RELEASING.md`, `SECURITY.md`, `CHANGELOG.md`
