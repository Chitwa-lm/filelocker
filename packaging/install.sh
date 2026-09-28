#!/usr/bin/env bash
# FileLocker installer
# Usage:
#   ./install.sh              — installs to ~/.local (no root needed)
#   ./install.sh --system     — installs to /usr/local (requires root)
#   ./install.sh --uninstall  — removes a previous installation

set -euo pipefail

APP_NAME="filelocker"
APP_VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# ---- Parse arguments ----
SYSTEM_INSTALL=false
UNINSTALL=false
for arg in "$@"; do
    case "$arg" in
        --system)   SYSTEM_INSTALL=true ;;
        --uninstall) UNINSTALL=true ;;
        --help|-h)
            echo "Usage: $0 [--system] [--uninstall]"
            exit 0
            ;;
    esac
done

# ---- Determine prefix ----
if $SYSTEM_INSTALL; then
    PREFIX="/usr/local"
    if [[ $EUID -ne 0 ]]; then
        echo "ERROR: --system install requires root. Run with sudo."
        exit 1
    fi
else
    PREFIX="${HOME}/.local"
fi

BIN_DIR="$PREFIX/bin"
LIB_DIR="$PREFIX/lib/$APP_NAME"
SHARE_DIR="$PREFIX/share"
APPS_DIR="$SHARE_DIR/applications"
ICONS_DIR="$SHARE_DIR/icons/hicolor/scalable/apps"
METAINFO_DIR="$SHARE_DIR/metainfo"
MANIFEST="$PREFIX/lib/$APP_NAME/.install_manifest"

# ---- Uninstall ----
if $UNINSTALL; then
    echo "Uninstalling FileLocker from $PREFIX..."
    if [[ ! -f "$MANIFEST" ]]; then
        echo "Manifest not found at $MANIFEST; nothing to remove."
        exit 1
    fi
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        rm -f "$file" && echo "  removed $file"
    done < "$MANIFEST"
    rm -f "$MANIFEST"
    rmdir --ignore-fail-on-non-empty "$LIB_DIR" 2>/dev/null || true
    # Update caches
    command -v update-desktop-database &>/dev/null && \
        update-desktop-database "$APPS_DIR" 2>/dev/null || true
    echo "Uninstall complete."
    exit 0
fi

# ---- Dependency check ----
echo "Checking dependencies..."
bash "$SCRIPT_DIR/check_deps.sh" || {
    echo ""
    echo "Please install the missing dependencies and re-run this script."
    exit 1
}

# ---- Install ----
echo ""
echo "Installing FileLocker $APP_VERSION to $PREFIX..."

INSTALLED_FILES=()

install_file() {
    local src="$1"
    local dst="$2"
    local mode="${3:-644}"
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    chmod "$mode" "$dst"
    INSTALLED_FILES+=("$dst")
    echo "  installed $dst"
}

# Launcher
install_file "$REPO_ROOT/bin/$APP_NAME" "$BIN_DIR/$APP_NAME" 755

# App source (copy src/filelocker tree to lib/filelocker)
mkdir -p "$LIB_DIR"
cp -r "$REPO_ROOT/src/filelocker" "$LIB_DIR/"
find "$LIB_DIR" -name "*.py" -exec chmod 644 {} \;
find "$LIB_DIR" -type d  -exec chmod 755 {} \;
# Track the lib directory files
while IFS= read -r -d '' f; do
    INSTALLED_FILES+=("$f")
done < <(find "$LIB_DIR" -type f -print0)

# Desktop file
install_file "$REPO_ROOT/data/$APP_NAME.desktop" \
             "$APPS_DIR/$APP_NAME.desktop" 644

# Icon
install_file \
    "$REPO_ROOT/data/icons/hicolor/scalable/apps/$APP_NAME.svg" \
    "$ICONS_DIR/$APP_NAME.svg" 644

# Metainfo
install_file "$REPO_ROOT/data/metainfo.xml" \
             "$METAINFO_DIR/io.github.$APP_NAME.metainfo.xml" 644

# Write manifest
printf '%s\n' "${INSTALLED_FILES[@]}" > "$MANIFEST"
chmod 600 "$MANIFEST"

# Update desktop and icon caches
command -v update-desktop-database &>/dev/null && \
    update-desktop-database "$APPS_DIR" 2>/dev/null && \
    echo "  updated desktop database" || true

command -v gtk-update-icon-cache &>/dev/null && \
    gtk-update-icon-cache -f -t "$SHARE_DIR/icons/hicolor" 2>/dev/null && \
    echo "  updated icon cache" || true

echo ""
echo "FileLocker $APP_VERSION installed successfully."
echo "Run it with:  filelocker"
echo "Or find it in your application launcher."
echo ""
echo "To uninstall:  $SCRIPT_DIR/install.sh --uninstall"
