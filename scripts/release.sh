#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"

if [[ -z "$VERSION" ]]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 0.1.0"
    exit 1
fi

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: Version must be in format X.Y.Z"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
TAP_DIR="$(dirname "$ROOT_DIR")/homebrew-macblock"

cd "$ROOT_DIR"

CURRENT_VERSION=$(grep -E '^__version__' src/macblock/_version.py | cut -d'"' -f2)

if [[ "$CURRENT_VERSION" != "$VERSION" ]]; then
    echo "Updating version from $CURRENT_VERSION to $VERSION..."
    sed -i '' "s/__version__ = \".*\"/__version__ = \"$VERSION\"/" src/macblock/_version.py
    sed -i '' "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml
fi

echo "Running tests..."
uv sync --dev
uv run python -m unittest discover -v tests/

echo "Building package..."
uv build

echo ""
echo "Next steps:"
echo "1. Commit the version changes:"
echo "   git add -A && git commit -m 'Release v$VERSION'"
echo ""
echo "2. Create and push the tag:"
echo "   git tag v$VERSION && git push origin main v$VERSION"
echo ""
echo "3. After the release is created, get the tarball SHA256:"
echo "   curl -sL https://github.com/SpyicyDev/macblock/archive/refs/tags/v$VERSION.tar.gz | shasum -a 256"
echo ""
echo "4. Update the Homebrew formula at:"
echo "   $TAP_DIR/Formula/macblock.rb"
echo "   - Update url to v$VERSION"
echo "   - Update sha256 with the hash from step 3"
echo ""
echo "5. Commit and push the formula update"
