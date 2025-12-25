# macblock task runner
#
# Install `just`: https://github.com/casey/just

set dotenv-load := false

default:
    @just --list

# --- Environment ---

sync:
    uv sync --dev


# --- Run ---

run *args:
    uv run macblock {{args}}

# --- Quality ---

fmt:
    uv run ruff format src/macblock tests

fmt-check:
    uv run ruff format --check src/macblock tests

lint:
    uv run ruff check src/macblock tests

lint-fix:
    uv run ruff check --fix src/macblock tests
    uv run ruff format src/macblock tests

typecheck:
    uv run pyright src/macblock

test *args="":
    uv run pytest {{args}}

test-cov:
    uv run pytest --cov=macblock --cov-report=term-missing --cov-report=html

check: fmt-check lint typecheck test

ci: fmt-check lint typecheck
    uv run pytest
    uv run macblock --version

# --- Release ---

# Prepare a release commit + tag.
# Usage: `just release 0.2.0`
release version:
    #!/usr/bin/env bash
    set -euo pipefail

    if [[ ! "{{version}}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Error: Version must be in format X.Y.Z" >&2
        exit 1
    fi

    if [[ -n "$(git status --porcelain)" ]]; then
        echo "Error: Working directory is not clean" >&2
        exit 1
    fi

    if ! command -v git-cliff >/dev/null 2>&1; then
        echo "Error: git-cliff is required (brew install git-cliff)" >&2
        exit 1
    fi

    echo "Updating version in pyproject.toml -> {{version}}"
    sed -i '' "s/^version = \".*\"/version = \"{{version}}\"/" pyproject.toml

    echo "Generating CHANGELOG.md"
    git cliff --config cliff.toml --tag "v{{version}}" --output CHANGELOG.md

    echo "Running checks"
    uv lock
    uv sync --dev --frozen
    uv run ruff format --check src/macblock tests
    uv run ruff check src/macblock tests
    uv run pyright src/macblock
    uv run pytest


    echo "Committing and tagging v{{version}}"
    git commit -m "chore(release): prepare v{{version}}"
    git tag "v{{version}}"

    echo
    echo "Prepared v{{version}}. To publish:"
    echo "  git push origin main v{{version}}"
