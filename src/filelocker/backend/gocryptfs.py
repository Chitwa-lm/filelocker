"""
GocryptfsBackend — wraps the gocryptfs CLI.

Security notes:
  - Passwords are passed via stdin pipe, never in argv.
  - All subprocess calls use list args (no shell=True).
  - Password bytearrays are zeroed after use.
  - gocryptfs output is captured; only sanitised error messages are
    forwarded to callers (no password echo possible).
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from .base import BackendAdapter, BackendError
from ..core.utils import zero_bytearray, is_mounted, force_unmount

log = logging.getLogger(__name__)

_GOCRYPTFS_BIN = "gocryptfs"
_FUSERMOUNT_BIN = "fusermount3"
_TIMEOUT = 30  # seconds for subprocess calls


class GocryptfsBackend(BackendAdapter):
    """Encryption backend using gocryptfs + FUSE."""

    # ------------------------------------------------------------------ #
    # Availability check                                                   #
    # ------------------------------------------------------------------ #

    def is_available(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [_GOCRYPTFS_BIN, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                version = result.stdout.strip().splitlines()[0]
                return True, version
            return False, "gocryptfs returned a non-zero exit code."
        except FileNotFoundError:
            return False, "gocryptfs not found. Install with: sudo apt install gocryptfs"
        except subprocess.TimeoutExpired:
            return False, "gocryptfs version check timed out."

    # ------------------------------------------------------------------ #
    # Init                                                                 #
    # ------------------------------------------------------------------ #

    def init_vault(self, vault_path: str, password: bytearray,
                   master_key_hex: str | None = None) -> None:
        """
        Initialise a new gocryptfs vault at *vault_path*.

        The directory must already exist.
        master_key_hex is accepted for API compatibility but not passed to
        gocryptfs -init (which derives its own master key from the password
        and scrypt). The recovery key is exported separately after init via
        gocryptfs -info or stored by the caller.
        """
        path = Path(vault_path)
        if not path.is_dir():
            raise BackendError(f"Vault path does not exist or is not a directory: {vault_path}")

        cmd = [_GOCRYPTFS_BIN, "-init", "-scryptn", "18", str(path)]

        try:
            result = self._run_with_password(cmd, password)
            if result.returncode != 0:
                err = self._format_error(result.stderr)
                raise BackendError(f"gocryptfs init failed: {err}")
        finally:
            zero_bytearray(password)

        log.info("Vault initialised at %s", vault_path)

    # ------------------------------------------------------------------ #
    # Mount                                                                #
    # ------------------------------------------------------------------ #

    def mount(self, vault_path: str, mountpoint: str,
              password: bytearray) -> None:
        """Mount vault at mountpoint using a background gocryptfs process."""
        import time

        mp = Path(mountpoint)
        mp.mkdir(mode=0o700, parents=True, exist_ok=True)

        if is_mounted(mountpoint):
            log.warning("Mountpoint %s is already mounted.", mountpoint)
            return

        # Do NOT use -fg: that blocks until unmount.
        # gocryptfs daemonises by default; it exits 0 once the mount is ready.
        cmd = [_GOCRYPTFS_BIN, str(vault_path), str(mp)]
        pw_bytes = bytes(password) + b"\n"

        try:
            result = subprocess.run(
                cmd,
                input=pw_bytes,
                capture_output=True,
                timeout=_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise BackendError("gocryptfs mount timed out.")
        finally:
            zero_bytearray(password)
            pw_bytes = b"\x00" * len(pw_bytes)

        if result.returncode != 0:
            err = self._format_error(result.stderr)
            if "wrong password" in err.lower() or "password incorrect" in err.lower() \
                    or "exit status 12" in err.lower() or result.returncode == 12:
                raise BackendError("Incorrect password.")
            raise BackendError(f"Mount failed: {err}")

        # Verify the mount actually appeared
        if not is_mounted(mountpoint):
            raise BackendError(
                "gocryptfs exited 0 but the filesystem is not visible in /proc/mounts."
            )

        log.info("Vault %s mounted at %s", vault_path, mountpoint)

    # ------------------------------------------------------------------ #
    # Unmount                                                              #
    # ------------------------------------------------------------------ #

    def unmount(self, mountpoint: str, force: bool = False) -> None:
        """Unmount via fusermount3."""
        if not is_mounted(mountpoint):
            log.debug("Mountpoint %s is not mounted; nothing to do.", mountpoint)
            return

        flags = ["-uz"] if force else ["-u"]
        try:
            result = subprocess.run(
                [_FUSERMOUNT_BIN] + flags + [mountpoint],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
            if result.returncode != 0:
                err = result.stderr.strip()
                raise BackendError(f"Unmount failed: {err}")
        except FileNotFoundError:
            raise BackendError("fusermount3 not found. Install fuse3.")
        except subprocess.TimeoutExpired:
            raise BackendError("Unmount timed out.")

        log.info("Unmounted %s", mountpoint)

    # ------------------------------------------------------------------ #
    # Change password                                                      #
    # ------------------------------------------------------------------ #

    def change_password(self, vault_path: str,
                        old_password: bytearray,
                        new_password: bytearray) -> None:
        """
        Change the vault password via gocryptfs -passwd.

        gocryptfs reads old password then new password from stdin,
        separated by a newline.
        """
        cmd = [_GOCRYPTFS_BIN, "-passwd", str(vault_path)]
        # Build combined stdin: old\nnew\n
        combined = bytearray()
        combined.extend(old_password)
        combined.extend(b"\n")
        combined.extend(new_password)
        combined.extend(b"\n")

        try:
            result = subprocess.run(
                cmd,
                input=bytes(combined),
                capture_output=True,
                timeout=_TIMEOUT,
            )
            if result.returncode != 0:
                err = self._format_error(result.stderr)
                raise BackendError(f"Password change failed: {err}")
        except subprocess.TimeoutExpired:
            raise BackendError("Password change timed out.")
        finally:
            zero_bytearray(old_password)
            zero_bytearray(new_password)
            zero_bytearray(combined)

        log.info("Password changed for vault at %s", vault_path)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _run_with_password(self, cmd: list[str],
                           password: bytearray) -> subprocess.CompletedProcess:
        """
        Run *cmd* with the password written to stdin.
        The password buffer is NOT zeroed here — the caller must do that
        in a finally block so it handles exceptions too.
        """
        pw_bytes = bytes(password) + b"\n"
        try:
            return subprocess.run(
                cmd,
                input=pw_bytes,
                capture_output=True,
                timeout=_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise BackendError("gocryptfs operation timed out.")
        finally:
            pw_bytes = b"\x00" * len(pw_bytes)

    @staticmethod
    def _format_error(stderr: bytes | str) -> str:
        """
        Decode stderr and return a clean error string.
        Strips control characters but preserves the actual error text so
        callers can act on it (e.g. detect wrong-password exit code 12).
        """
        if isinstance(stderr, bytes):
            text = stderr.decode("utf-8", errors="replace")
        else:
            text = stderr
        # Remove ANSI colour codes and strip blank lines
        import re
        text = re.sub(r"\x1b\[[0-9;]*m", "", text)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return " | ".join(lines) if lines else "Unknown error (check system logs)."

    @staticmethod
    def _sanitise_error(stderr: bytes | str) -> str:
        """Alias kept for backward compatibility."""
        return GocryptfsBackend._format_error(stderr)
