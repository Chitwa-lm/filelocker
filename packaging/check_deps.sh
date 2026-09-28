#!/usr/bin/env bash
# Dependency checker for FileLocker.
# Exits 0 if all deps present, 1 if any are missing (and prints the apt line).

set -euo pipefail

MISSING=()

check_bin() {
    local bin="$1"
    if ! command -v "$bin" &>/dev/null; then
        MISSING+=("$bin")
    fi
}

check_python_module() {
    local module="$1"
    if ! python3 -c "import $module" &>/dev/null; then
        MISSING+=("python3-$module")
    fi
}

check_gir() {
    local ns="$1"
    local ver="$2"
    if ! python3 -c "
import gi
gi.require_version('$ns', '$ver')
from gi.repository import $ns
" &>/dev/null; then
        MISSING+=("gir1.2-$(echo $ns | tr '[:upper:]' '[:lower:]')-$ver")
    fi
}

echo "Checking FileLocker dependencies..."

check_bin "gocryptfs"
check_bin "fusermount3"
check_bin "python3"
check_python_module "gi"
check_gir "Gtk" "4.0"
check_gir "Adw" "1"

# dbus-python is optional but recommended
if ! python3 -c "import dbus" &>/dev/null; then
    echo "  [WARN] dbus-python not found — screen-lock auto-lock will be disabled."
    echo "         Install with: sudo apt install python3-dbus"
fi

if [ ${#MISSING[@]} -eq 0 ]; then
    echo "  All required dependencies found."
    exit 0
else
    echo ""
    echo "  Missing dependencies: ${MISSING[*]}"
    echo ""
    echo "  Install them with:"
    echo "    sudo apt install gocryptfs fuse3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-dbus"
    echo ""
    exit 1
fi
