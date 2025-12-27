# AGENTS.md — macblock

This repository is a Python CLI + daemon for macOS that manages a local `dnsmasq` DNS sinkhole.
Agents working here should prefer the repo’s task runner (`just`) and tooling (`uv`, `ruff`, `pyright`, `pytest`).

## Tooling snapshot

- Python: `>=3.10` (package), `.python-version` currently `3.12.1`
- Package/deps runner: `uv`
- Task runner: `just` (see `justfile`)
- Formatting + lint: `ruff` (`ruff format`, `ruff check`)
- Type checking: `pyright`
- Tests: `pytest` (see `[tool.pytest.ini_options]` in `pyproject.toml`)

## Quick start (local)

- Install local tools (macOS): `brew install just direnv`
- Enable env automation: `direnv allow` (uses `.envrc`)
- Install deps: `just sync`
- Run CI-equivalent checks: `just ci` (or `just check` for tests too)

Notes:
- `.envrc` creates `.venv`, runs `uv sync --dev`, and sets `PYTHONPATH="$PWD/src"`.
- When in doubt, run commands from repo root.

## Commands

Prefer the `just` recipes (they match CI).

### Dependencies / environment

- Install dev dependencies: `just sync`
- Equivalent: `uv sync --dev`

### Run the CLI

- List tasks: `just`
- Run the CLI: `just run status`
- Equivalent: `uv run macblock status`
- Module form (helpful during dev): `uv run python -m macblock status`

### Format / lint / typecheck

- Format (write changes): `just fmt`
- Format check (no changes): `just fmt-check`
- Lint: `just lint`
- Lint auto-fix + format: `just lint-fix`
- Typecheck: `just typecheck`

Underlying commands (used in CI):
- `uv run ruff format --check src/macblock tests`
- `uv run ruff check src/macblock tests`
- `uv run pyright src/macblock`

### Tests

- Run full suite: `just test`
- With args passthrough: `just test "-k parser"`
- With coverage (local): `just test-cov`

Single-test workflows (most useful for agents):
- Single file: `uv run pytest tests/test_cli.py`
- Single test: `uv run pytest tests/test_cli.py::test_parser_status`
- Single class method: `uv run pytest tests/test_daemon.py::TestSomething::test_case`
- Keyword filter: `uv run pytest -k "parser"`

Pytest configuration:
- Tests live in `tests/`
- `pythonpath = ["src"]` (imports should work when running from repo root)
- Default opts include `-v --tb=short`

### Build

- Build sdist/wheel: `uv build`

### "All checks"

- Local quality gate (includes tests): `just check`
- CI subset (format/lint/typecheck + tests + version): `just ci`

## Git workflow (agents)

Agents should commit code in logical chunks without being prompted.

- After completing a coherent change (one fix/feature/refactor), create a commit.
- Prefer small commits that keep `main`/branch buildable; avoid mixing unrelated changes.
- Before committing, run the relevant quality gate (`just check` or a targeted subset like `just fmt` + `just test "-k ..."`).
- Use Conventional Commits (see `CONTRIBUTING.md`): `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`, `test: ...`, `chore: ...`.
- Never commit secrets (e.g., `.env`, credentials files) or machine-specific artifacts.

## CI behavior (GitHub Actions)

CI runs on macOS for Python `3.10`, `3.11`, `3.12` and executes:

- `uv sync --dev`
- `uv run ruff format --check src/macblock tests`
- `uv run ruff check src/macblock tests`
- `uv run pyright src/macblock`
- `uv run pytest --cov=macblock --cov-report=xml`
- `uv run macblock --version`

Agents should keep changes compatible with Python 3.10+ and macOS.

## Repository layout (high signal)

- `src/macblock/`: main package
  - `cli.py`: entrypoint + argument parsing + top-level error handling
  - `errors.py`: repo-defined exception types (`MacblockError`, etc.)
  - `exec.py`: subprocess helper returning a `RunResult`
  - `install.py`, `launchd.py`, `system_dns.py`: macOS integration (privileged)
- `tests/`: pytest suite
- `justfile`: canonical dev commands
- `.github/workflows/`: CI and release workflows

## Code style and conventions

### Formatting

- Use `ruff format` via `just fmt` / `just fmt-check`.
- Do not introduce `black`, `isort`, or `mypy` configs unless explicitly requested.
- Keep diffs small and focused; avoid drive-by refactors.

### Imports

Existing files generally follow:

- `from __future__ import annotations` at the very top for new modules
- Standard library imports first
- Then local imports using absolute package paths: `from macblock.<module> import ...`

Avoid relative imports unless there is a strong reason.

### Types

- Prefer modern built-in generics and unions: `list[str]`, `dict[str, str]`, `str | None`.
- Keep `pyright` clean; don’t silence errors with `Any`-style escapes.
- When interacting with subprocess output, be explicit about `bytes` vs `str` (see `src/macblock/exec.py`).

### Naming

- `snake_case` for functions/variables
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- Private helpers use a leading underscore (common in `cli.py`).

### Error handling

- Use `MacblockError` (and subclasses) for user-facing failures that should print a clean message.
  - `src/macblock/cli.py` catches `MacblockError` and prints `error: ...` with exit code `1`.
  - `UnsupportedPlatformError` and `PrivilegeError` map to exit code `2`.
- Prefer catching specific exceptions; avoid broad `except Exception` unless you re-raise or add strong context.
- When wrapping a failure that should propagate, raise a `MacblockError` with actionable guidance.

### Subprocesses

- Prefer `src/macblock/exec.py:run()` for short commands; it returns a structured `RunResult`.
- Timeouts should be intentional and handled (see timeout behavior in `RunResult`).

### Filesystem / privilege

- Many commands touch macOS system paths (e.g., `/Library/...`, `/var/db/...`) and can require root.
- Tests should not perform privileged operations or mutate system DNS.
  - Prefer dependency injection / monkeypatching / temp directories when adding tests.

## Release / versioning (maintainers)

- Releases are tag-based: `vX.Y.Z`.
- `just release X.Y.Z` updates `pyproject.toml`, regenerates `CHANGELOG.md`, runs checks, commits, and tags.

## Cursor / Copilot rules

- Cursor rules: not present (`.cursor/rules/` and `.cursorrules` not found).
- Copilot instructions: not present (`.github/copilot-instructions.md` not found).
