"""Utility helpers: password handling, process inspection, stale-mount detection."""

from __future__ import annotations

import os
import subprocess
import logging
from pathlib import Path

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Password helpers                                                     #
# ------------------------------------------------------------------ #

def zero_bytearray(buf: bytearray) -> None:
    """Overwrite a bytearray in place with null bytes."""
    for i in range(len(buf)):
        buf[i] = 0


def str_to_bytearray(s: str) -> bytearray:
    """Encode a str to a mutable bytearray."""
    return bytearray(s.encode("utf-8"))


# ------------------------------------------------------------------ #
# Process / lsof helpers                                              #
# ------------------------------------------------------------------ #

def processes_using_path(path: str) -> list[dict]:
    """
    Return a list of dicts describing processes with open files under *path*.
    Uses /proc scanning — no external tools required.

    Each dict: {"pid": int, "name": str, "open_files": list[str]}
    """
    results: list[dict] = []
    path = os.path.realpath(path)

    for pid_dir in Path("/proc").iterdir():
        if not pid_dir.name.isdigit():
            continue
        pid = int(pid_dir.name)
        fd_dir = pid_dir / "fd"
        try:
            open_files = []
            for fd in fd_dir.iterdir():
                try:
                    target = os.readlink(fd)
                    if target.startswith(path):
                        open_files.append(target)
                except OSError:
                    pass
            if open_files:
                try:
                    comm = (pid_dir / "comm").read_text().strip()
                except OSError:
                    comm = "unknown"
                results.append({"pid": pid, "name": comm, "open_files": open_files})
        except PermissionError:
            pass
        except OSError:
            pass

    return results


# ------------------------------------------------------------------ #
# Mount helpers                                                        #
# ------------------------------------------------------------------ #

def is_mounted(mountpoint: str) -> bool:
    """Check /proc/mounts to see if *mountpoint* is currently mounted."""
    mp = os.path.realpath(mountpoint)
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and os.path.realpath(parts[1]) == mp:
                    return True
    except OSError:
        pass
    return False


def is_fuse_healthy(mountpoint: str) -> bool:
    """
    Return True only if the mountpoint is mounted AND the FUSE daemon is
    responsive (i.e. a stat() call succeeds without ENOTCONN / ENODEV).
    """
    if not is_mounted(mountpoint):
        return False
    try:
        os.stat(mountpoint)
        return True
    except OSError as e:
        import errno
        # ENOTCONN = transport endpoint not connected (dead FUSE mount)
        # ENODEV   = no such device (FUSE device gone)
        if e.errno in (errno.ENOTCONN, errno.ENODEV):
            return False
        # Any other error (EACCES etc.) means it exists but we can't stat it —
        # treat as not healthy from our perspective.
        return False


def find_stale_mounts(runtime_dir: str) -> list[str]:
    """
    Scan the filelocker runtime directory for mountpoints that are either:
      - Still listed in /proc/mounts (normal stale mount), OR
      - Listed in /proc/mounts but FUSE is dead (ENOTCONN), OR
      - Directories that exist but are NOT in /proc/mounts at all
        (leftover empty mountpoint dirs — safe to rmdir).

    Returns a list of mountpoint paths that need cleanup.
    """
    stale: list[str] = []
    base = Path(runtime_dir)
    if not base.exists():
        return stale
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        mp = str(entry)
        if is_mounted(mp):
            # In /proc/mounts — check if FUSE is actually alive
            if not is_fuse_healthy(mp):
                stale.append(mp)
            # If healthy it's a legitimately mounted vault; leave it alone.
        else:
            # Not in /proc/mounts but dir exists — leftover from previous run
            stale.append(mp)
    return stale


def force_unmount(mountpoint: str) -> tuple[bool, str]:
    """
    Lazy unmount via fusermount3 -uz.  Returns (success, message).
    Also handles dead FUSE mounts (ENOTCONN) by falling back to
    a plain rmdir if fusermount3 cannot detach the endpoint.
    """
    import errno as _errno

    # First try a proper lazy unmount
    try:
        result = subprocess.run(
            ["fusermount3", "-uz", mountpoint],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Clean up the now-empty directory
            try:
                os.rmdir(mountpoint)
            except OSError:
                pass
            return True, "Unmounted successfully."
        # fusermount3 failed — fall through to rmdir attempt
        fuse_err = result.stderr.strip()
    except FileNotFoundError:
        return False, "fusermount3 not found."
    except subprocess.TimeoutExpired:
        return False, "Unmount timed out."

    # If the FUSE endpoint is already dead (ENOTCONN), the kernel has already
    # detached the filesystem internally.  We just need to remove the directory.
    try:
        os.rmdir(mountpoint)
        return True, "Removed dead FUSE mountpoint directory."
    except OSError as e:
        if e.errno == _errno.ENOTCONN:
            # Directory is in a broken state; try lazy unmount one more time
            # via umount (may need no privileges for FUSE)
            try:
                subprocess.run(
                    ["umount", "-l", mountpoint],
                    capture_output=True, timeout=5
                )
                os.rmdir(mountpoint)
                return True, "Cleaned up dead FUSE mount."
            except Exception:
                pass
        return False, f"fusermount3 error: {fuse_err}; rmdir error: {e}"


# ------------------------------------------------------------------ #
# Password strength scorer                                             #
# ------------------------------------------------------------------ #

def score_password(password: str) -> tuple[int, str]:
    """
    Simple password strength scorer (0-4).
    Returns (score, label).  No external deps.

    Scoring:
      +1 length >= 8
      +1 length >= 12
      +1 has digits and letters
      +1 has mixed case and symbols
    """
    if not password:
        return 0, "Too short"

    score = 0
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_symbol = any(not c.isalnum() for c in password)

    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1
    if has_digit and (has_lower or has_upper):
        score += 1
    if has_symbol and has_lower and has_upper:
        score += 1

    labels = {0: "Very weak", 1: "Weak", 2: "Fair", 3: "Strong", 4: "Very strong"}
    return score, labels[score]


# ------------------------------------------------------------------ #
# XDG helpers                                                          #
# ------------------------------------------------------------------ #

def get_runtime_dir() -> str:
    """Return the filelocker subdirectory under XDG_RUNTIME_DIR."""
    base = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    path = Path(base) / "filelocker"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return str(path)


def get_config_dir() -> str:
    """Return ~/.config/filelocker, creating it if needed."""
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    path = Path(base) / "filelocker"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return str(path)


def get_data_dir() -> str:
    """Return ~/.local/share/filelocker/vaults, creating it if needed."""
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    path = Path(base) / "filelocker" / "vaults"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return str(path)
