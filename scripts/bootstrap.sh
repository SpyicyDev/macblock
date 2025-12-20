#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  echo "Do not run this installer as root." >&2
  exit 1
fi

TAP="${MACBLOCK_TAP:-}"       # e.g. "yourorg/macblock"
FORMULA="${MACBLOCK_FORMULA:-macblock}"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required to install ${FORMULA}." >&2
  echo "Install Homebrew first: https://brew.sh" >&2
  exit 1
fi

if [[ -z "${TAP}" ]]; then
  echo "Set MACBLOCK_TAP to your Homebrew tap, e.g.:" >&2
  echo "  MACBLOCK_TAP=yourorg/macblock ./scripts/bootstrap.sh" >&2
  exit 1
fi

echo "+ brew tap ${TAP}"
brew tap "${TAP}"

echo "+ brew install ${FORMULA}"
brew install "${FORMULA}"

echo
echo "Next:" 
echo "  sudo ${FORMULA} install" 
echo
