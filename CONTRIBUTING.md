# Contributing

## Prerequisites

- macOS (this project configures system DNS and launchd)
- `uv` (Python tooling)
- `just` (task runner)

Optional but recommended:
- `direnv` (auto environment setup)

## Setup

```bash
git clone https://github.com/SpyicyDev/macblock.git
cd macblock

# Optional: automatically sync deps + set env vars
brew install direnv

direnv allow

# Install deps + pre-commit hooks
just setup
```

## Common commands

```bash
just            # list available tasks
just ci         # format-check, lint, pyright, tests
just lint-fix   # auto-fix lint issues + format
just test       # run pytest
just run status # run the CLI
```

## Commit messages

Use Conventional Commits:

- `feat: ...`
- `fix: ...`
- `docs: ...`
- `refactor: ...`
- `test: ...`
- `chore: ...`

## Release process (maintainers)

See `docs/RELEASING.md`.
