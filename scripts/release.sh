#!/usr/bin/env bash
# Usage: ./scripts/release.sh <version>
#   e.g. ./scripts/release.sh 0.3.4
#
# What it does:
#   1. Validates prerequisites (gh, git, jq, right repo, right branch)
#   2. Bumps version in plugin.json + marketplace.json
#   3. Dates the [Unreleased] section in CHANGELOG.md → [<version>]
#   4. Commits + pushes the version bump to main
#   5. Tags + pushes v<version>
#   6. Builds a curated zip from the tag
#   7. Creates the GitHub release (latest flag on) with the zip attached

set -euo pipefail

# ── args ──────────────────────────────────────────────────────────────────────
VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "Usage: $0 <version>  (e.g. $0 0.3.4)" >&2
  exit 1
fi
TAG="v${VERSION}"

# ── resolve repo root ──────────────────────────────────────────────────────────
REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# ── prerequisites ──────────────────────────────────────────────────────────────
for cmd in gh git jq zip; do
  command -v "$cmd" &>/dev/null || { echo "ERROR: '$cmd' not found in PATH" >&2; exit 1; }
done

# Ensure gh is authenticated as a user with push access
GH_USER="$(gh api user --jq '.login' 2>/dev/null)"
echo "  gh user : $GH_USER"

# Must be on main (or an explicit release branch)
CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" != "main" ]]; then
  echo "ERROR: run this from main (currently on '$CURRENT_BRANCH')" >&2
  exit 1
fi

# Pull latest main
echo "→ pulling origin/main"
git pull origin main --ff-only

# Tag must not already exist locally or remotely
if git rev-parse "$TAG" &>/dev/null; then
  echo "ERROR: local tag '$TAG' already exists — delete it first: git tag -d $TAG" >&2
  exit 1
fi
if git ls-remote --tags origin "$TAG" | grep -q "$TAG"; then
  echo "ERROR: remote tag '$TAG' already exists on origin" >&2
  exit 1
fi

# CHANGELOG must have an [Unreleased] section
if ! grep -q '^\#\# \[Unreleased\]' CHANGELOG.md; then
  echo "ERROR: no '## [Unreleased]' section found in CHANGELOG.md" >&2
  exit 1
fi

# ── bump versions ──────────────────────────────────────────────────────────────
echo "→ bumping plugin.json + marketplace.json to $VERSION"
OLD_VERSION="$(jq -r '.version' .claude-plugin/plugin.json)"
if [[ "$OLD_VERSION" == "$VERSION" ]]; then
  echo "ERROR: plugin.json is already at $VERSION — did you forget to bump?" >&2
  exit 1
fi

TODAY="$(date +%Y-%m-%d)"

# plugin.json
jq --arg v "$VERSION" '.version = $v' .claude-plugin/plugin.json > /tmp/plugin.json.tmp
mv /tmp/plugin.json.tmp .claude-plugin/plugin.json

# marketplace.json  (plugins[].version)
jq --arg v "$VERSION" '.plugins[].version = $v' .claude-plugin/marketplace.json > /tmp/marketplace.json.tmp
mv /tmp/marketplace.json.tmp .claude-plugin/marketplace.json

# CHANGELOG.md — rename [Unreleased] → [<version>] — <date>
sed -i.bak "s/^## \[Unreleased\]/## [$VERSION] — $TODAY/" CHANGELOG.md
rm -f CHANGELOG.md.bak

# ── commit + push version bump ─────────────────────────────────────────────────
echo "→ committing version bump"
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json CHANGELOG.md
git commit -m "release: $VERSION"

echo "→ pushing version bump to origin/main"
git push origin main

# ── tag ────────────────────────────────────────────────────────────────────────
echo "→ tagging $TAG"
git tag -a "$TAG" -m "apex $VERSION"
git push origin "$TAG"

# ── build zip ─────────────────────────────────────────────────────────────────
ZIP_DIR="/tmp/apex-${VERSION}"
ZIP_PATH="${HOME}/Downloads/apex-${VERSION}.zip"
echo "→ building $ZIP_PATH"
rm -rf "$ZIP_DIR"
mkdir -p "$ZIP_DIR"
git archive --format=tar "$TAG" | tar -x -C "$ZIP_DIR"
( cd /tmp && zip -rq "$ZIP_PATH" "apex-${VERSION}" )
echo "   size: $(du -sh "$ZIP_PATH" | cut -f1)"

# ── github release ─────────────────────────────────────────────────────────────
echo "→ creating GitHub release $TAG"
RELEASE_URL="$(gh release create "$TAG" "$ZIP_PATH" \
  --repo vancourse/apex \
  --title "apex $VERSION" \
  --generate-notes \
  --latest \
  --verify-tag)"

echo ""
echo "✓ Released $TAG → $RELEASE_URL"
echo "  zip: $ZIP_PATH"
