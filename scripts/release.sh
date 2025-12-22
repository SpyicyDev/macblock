#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"

if [[ -z "$VERSION" ]]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 0.2.0"
    echo ""
    echo "This script:"
    echo "  1. Updates version in _version.py and pyproject.toml"
    echo "  2. Runs tests"
    echo "  3. Commits the version bump"
    echo "  4. Creates and pushes the tag"
    echo ""
    echo "The GitHub Action will then:"
    echo "  - Create a GitHub release with artifacts"
    echo "  - Update the Homebrew formula automatically"
    exit 1
fi

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: Version must be in format X.Y.Z"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
    echo "Error: Working directory is not clean. Commit or stash changes first."
    exit 1
fi

CURRENT_VERSION=$(grep -E '^__version__' src/macblock/_version.py | cut -d'"' -f2)
echo "Current version: $CURRENT_VERSION"
echo "New version: $VERSION"
echo ""

if [[ "$CURRENT_VERSION" == "$VERSION" ]]; then
    echo "Version is already $VERSION"
else
    echo "Updating version..."
    sed -i '' "s/__version__ = \".*\"/__version__ = \"$VERSION\"/" src/macblock/_version.py
    sed -i '' "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml
fi

echo "Running tests..."
uv sync --dev
uv run pyright src/macblock
uv run ruff check src/macblock --ignore E402
uv run python -m unittest discover -v tests/

echo ""
echo "Committing version bump..."
git add src/macblock/_version.py pyproject.toml
git commit -m "Release v$VERSION" || echo "Nothing to commit"

echo ""
echo "Creating tag v$VERSION..."
git tag "v$VERSION"

echo ""
read -p "Push to origin? [y/N] " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    git push origin main
    git push origin "v$VERSION"
    echo ""
    echo "Done! The GitHub Action will now:"
    echo "  1. Run tests"
    echo "  2. Create a GitHub release"
    echo "  3. Update the Homebrew formula (if HOMEBREW_TAP_TOKEN is set)"
    echo ""
    echo "Monitor progress at:"
    echo "  https://github.com/SpyicyDev/macblock/actions"
else
    echo ""
    echo "Tag created locally. To push manually:"
    echo "  git push origin main"
    echo "  git push origin v$VERSION"
fi
