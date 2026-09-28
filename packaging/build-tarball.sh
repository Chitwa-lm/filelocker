#!/usr/bin/env bash
# Build a reproducible release tarball.
# Output: dist/filelocker-<version>.tar.gz  + SHA256SUMS

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
VERSION="$(python3 -c "import sys; sys.path.insert(0,'$REPO_ROOT/src'); from filelocker import __version__; print(__version__)")"
DIST_DIR="$REPO_ROOT/dist"
ARCHIVE_NAME="filelocker-$VERSION"
ARCHIVE_PATH="$DIST_DIR/$ARCHIVE_NAME.tar.gz"

mkdir -p "$DIST_DIR"

echo "Building $ARCHIVE_NAME..."

# Reproducible: fixed mtime, sorted, no user/group names
tar \
    --create \
    --gzip \
    --file="$ARCHIVE_PATH" \
    --directory="$REPO_ROOT" \
    --transform="s|^|$ARCHIVE_NAME/|" \
    --sort=name \
    --mtime="2026-09-28T00:00:00Z" \
    --owner=0 --group=0 --numeric-owner \
    bin/ \
    src/ \
    data/ \
    packaging/install.sh \
    packaging/uninstall.sh \
    packaging/check_deps.sh \
    README.md \
    LICENSE \
    SPEC.md

echo "Created $ARCHIVE_PATH"

# SHA256
(cd "$DIST_DIR" && sha256sum "$ARCHIVE_NAME.tar.gz" > SHA256SUMS)
echo "SHA256SUMS written."

# Optional GPG signature
if command -v gpg &>/dev/null && [[ -n "${FILELOCKER_GPG_KEY:-}" ]]; then
    gpg --detach-sign --armor \
        --local-user "$FILELOCKER_GPG_KEY" \
        "$ARCHIVE_PATH"
    echo "GPG signature created: $ARCHIVE_PATH.asc"
else
    echo "Skipping GPG signature (set FILELOCKER_GPG_KEY env var to enable)."
fi

echo ""
echo "Done. Artifacts in $DIST_DIR/"
