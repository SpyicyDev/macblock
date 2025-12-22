# Releasing macblock

## Prerequisites

### Set up Deploy Key (one-time)

To enable automatic Homebrew formula updates:

1. **Generate an SSH key pair**:
   ```bash
   ssh-keygen -t ed25519 -C "macblock-deploy" -f macblock-deploy-key -N ""
   ```

2. **Add the public key to homebrew-macblock**:
   - Go to https://github.com/SpyicyDev/homebrew-macblock/settings/keys
   - Click "Add deploy key"
   - Title: `macblock-release`
   - Key: paste contents of `macblock-deploy-key.pub`
   - Check "Allow write access"
   - Click "Add key"

3. **Add the private key to macblock**:
   - Go to https://github.com/SpyicyDev/macblock/settings/secrets/actions
   - Click "New repository secret"
   - Name: `HOMEBREW_DEPLOY_KEY`
   - Value: paste contents of `macblock-deploy-key` (the private key)
   - Click "Add secret"

4. **Delete the local key files**:
   ```bash
   rm macblock-deploy-key macblock-deploy-key.pub
   ```

Without this setup, releases will still work but you'll need to manually update the Homebrew formula.

## Creating a Release

### Option 1: Use the release script (recommended)

```bash
./scripts/release.sh 0.2.0
```

The script will:
1. Update version in `_version.py` and `pyproject.toml`
2. Run all tests
3. Commit the version bump
4. Create the git tag
5. Optionally push to origin

### Option 2: Manual release

```bash
# Update version
sed -i '' 's/__version__ = ".*"/__version__ = "0.2.0"/' src/macblock/_version.py
sed -i '' 's/^version = ".*"/version = "0.2.0"/' pyproject.toml

# Test
uv sync --dev
uv run python -m unittest discover -v tests/

# Commit and tag
git add -A
git commit -m "Release v0.2.0"
git tag v0.2.0
git push origin main v0.2.0
```

## What happens after pushing a tag

The GitHub Action will automatically:

1. **Test**: Run pyright, ruff, and unit tests
2. **Verify**: Check that tag version matches package version
3. **Release**: Create a GitHub release with wheel and sdist
4. **Update Homebrew**: Push formula update to homebrew-macblock repo

## Monitoring

Watch the release progress at:
https://github.com/SpyicyDev/macblock/actions

## If Homebrew update fails

If the automatic update fails (e.g., deploy key not configured), manually update:

```bash
# Get the SHA256
curl -sL https://github.com/SpyicyDev/macblock/archive/refs/tags/v0.2.0.tar.gz | shasum -a 256

# Update the formula
cd ../homebrew-macblock
# Edit Formula/macblock.rb with new version and SHA256
git commit -am "Update to v0.2.0"
git push origin main
```

## Version format

Use semantic versioning: `MAJOR.MINOR.PATCH`

- MAJOR: Breaking changes
- MINOR: New features, backward compatible
- PATCH: Bug fixes, backward compatible
