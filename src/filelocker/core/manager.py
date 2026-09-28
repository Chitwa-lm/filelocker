"""
VaultManager — high-level operations on vaults.

This is the single entry-point the GUI and CLI use.  It owns:
  - The vault registry
  - The backend adapter
  - The active-mounts table (in-memory + runtime dir)
  - Stale-mount recovery at startup
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Callable

from .vault import Vault, VaultStatus
from .registry import Registry
from .recovery import generate_recovery_key, raw_key_to_gocryptfs_hex
from .utils import (
    get_config_dir,
    get_data_dir,
    get_runtime_dir,
    find_stale_mounts,
    force_unmount,
    is_mounted,
    is_fuse_healthy,
    str_to_bytearray,
    zero_bytearray,
    processes_using_path,
)
from ..backend.gocryptfs import GocryptfsBackend
from ..backend.base import BackendError

log = logging.getLogger(__name__)


class VaultError(Exception):
    """Raised when a vault operation fails."""


class VaultManager:
    """
    Orchestrates vault lifecycle operations.

    Usage:
        mgr = VaultManager()
        mgr.create_vault("Personal", password_ba)
        mgr.unlock_vault(vault_id, password_ba)
        mgr.lock_vault(vault_id)
    """

    def __init__(
        self,
        config_dir: str | None = None,
        data_dir: str | None = None,
        runtime_dir: str | None = None,
        backend: GocryptfsBackend | None = None,
    ) -> None:
        self._config_dir = config_dir or get_config_dir()
        self._data_dir = data_dir or get_data_dir()
        self._runtime_dir = runtime_dir or get_runtime_dir()
        self._registry = Registry(self._config_dir)
        self._backend = backend or GocryptfsBackend()
        # vault_id -> mountpoint path for currently mounted vaults
        self._active: dict[str, str] = {}

        self._recover_stale_mounts()

    # ------------------------------------------------------------------ #
    # Public: vault listing                                                #
    # ------------------------------------------------------------------ #

    def list_vaults(self, include_stealth: bool = False) -> list[Vault]:
        """Return registered vaults, refreshing unlock status from /proc/mounts."""
        vaults = self._registry.all() if include_stealth else self._registry.visible()
        for v in vaults:
            mp = self._mountpoint_for(v.id)
            if is_fuse_healthy(mp):
                v.status = VaultStatus.UNLOCKED
                v.mountpoint = mp
                self._active[v.id] = mp
            else:
                v.status = VaultStatus.LOCKED
                v.mountpoint = None
                self._active.pop(v.id, None)
        return vaults

    def get_vault(self, vault_id: str) -> Vault:
        """Return a vault with its current runtime status populated."""
        vault = self._registry.get(vault_id)
        mp = self._mountpoint_for(vault_id)
        if is_fuse_healthy(mp):
            vault.status = VaultStatus.UNLOCKED
            vault.mountpoint = mp
            self._active[vault_id] = mp
        else:
            vault.status = VaultStatus.LOCKED
            vault.mountpoint = None
        return vault

    # ------------------------------------------------------------------ #
    # Public: create                                                       #
    # ------------------------------------------------------------------ #

    def create_vault(
        self,
        name: str,
        password: bytearray,
        location: str | None = None,
        stealth: bool = False,
    ) -> tuple[Vault, str]:
        """
        Create a new vault.

        Args:
            name:      Display name.
            password:  Password as a bytearray (will be zeroed).
            location:  Parent directory for the vault dir.  Defaults to
                       ~/.local/share/filelocker/vaults.
            stealth:   If True, prefix the vault dir with a dot.

        Returns:
            (vault, mnemonic) — the mnemonic is the recovery key the user
            must write down.  Show it exactly once.
        """
        if not name.strip():
            raise VaultError("Vault name cannot be empty.")
        if len(password) < 8:
            raise VaultError("Password must be at least 8 characters.")

        vault_id = secrets.token_hex(4)  # 8 hex chars
        parent = Path(location or self._data_dir)
        prefix = "." if stealth else ""
        vault_path = parent / f"{prefix}{vault_id}"
        vault_path.mkdir(mode=0o700, parents=True, exist_ok=False)

        # Generate a recovery mnemonic for the user to write down.
        # This is a 256-bit random value encoded as 24 words — it serves as
        # a human-friendly backup reminder token displayed once at creation.
        # The actual vault decryption key is managed entirely by gocryptfs.
        _raw_key, mnemonic = generate_recovery_key()

        try:
            self._backend.init_vault(str(vault_path), password)
        except BackendError as exc:
            # Clean up empty directory on failure
            vault_path.rmdir()
            raise VaultError(str(exc)) from exc
        finally:
            zero_bytearray(password)

        vault = Vault(
            id=vault_id,
            name=name.strip(),
            path=str(vault_path),
            stealth=stealth,
        )
        self._registry.add(vault)
        log.info("Created vault %r at %s", name, vault_path)
        return vault, mnemonic

    # ------------------------------------------------------------------ #
    # Public: unlock                                                       #
    # ------------------------------------------------------------------ #

    def unlock_vault(self, vault_id: str, password: bytearray) -> str:
        """
        Mount the vault and return the mountpoint path.

        Raises VaultError on wrong password or mount failure.
        """
        vault = self._registry.get(vault_id)
        mp = self._mountpoint_for(vault_id)

        if is_fuse_healthy(mp):
            log.debug("Vault %s already mounted and healthy at %s", vault_id, mp)
            vault.status = VaultStatus.UNLOCKED
            vault.mountpoint = mp
            self._active[vault_id] = mp
            return mp

        # If the mountpoint exists but is dead, clean it up before remounting
        if is_mounted(mp) and not is_fuse_healthy(mp):
            log.warning("Dead FUSE mount at %s; cleaning up before remount.", mp)
            force_unmount(mp)

        try:
            self._backend.mount(vault.path, mp, password)
        except BackendError as exc:
            raise VaultError(str(exc)) from exc
        finally:
            zero_bytearray(password)

        vault.status = VaultStatus.UNLOCKED
        vault.mountpoint = mp
        self._active[vault_id] = mp
        log.info("Vault %s unlocked at %s", vault_id, mp)
        return mp

    # ------------------------------------------------------------------ #
    # Public: lock                                                         #
    # ------------------------------------------------------------------ #

    def lock_vault(self, vault_id: str, force: bool = False) -> None:
        """
        Unmount the vault.

        If *force* is False and processes hold files open, raises
        VaultError with details.  If *force* is True, uses lazy unmount.
        """
        vault = self._registry.get(vault_id)
        mp = self._active.get(vault_id) or self._mountpoint_for(vault_id)

        if not is_mounted(mp):
            vault.status = VaultStatus.LOCKED
            vault.mountpoint = None
            self._active.pop(vault_id, None)
            return

        if not force:
            busy = processes_using_path(mp)
            if busy:
                names = ", ".join(f"{p['name']}({p['pid']})" for p in busy[:5])
                raise VaultError(
                    f"Cannot lock: files are open in {names}. "
                    "Close them or use force-lock."
                )

        try:
            self._backend.unmount(mp, force=force)
        except BackendError as exc:
            raise VaultError(str(exc)) from exc

        vault.status = VaultStatus.LOCKED
        vault.mountpoint = None
        self._active.pop(vault_id, None)
        log.info("Vault %s locked.", vault_id)

    # ------------------------------------------------------------------ #
    # Public: lock all                                                     #
    # ------------------------------------------------------------------ #

    def lock_all(self, force: bool = False) -> list[tuple[str, str]]:
        """
        Lock every currently unlocked vault.

        Returns a list of (vault_id, error_message) for any that failed.
        """
        errors: list[tuple[str, str]] = []
        for vault_id in list(self._active.keys()):
            try:
                self.lock_vault(vault_id, force=force)
            except VaultError as exc:
                errors.append((vault_id, str(exc)))
        return errors

    # ------------------------------------------------------------------ #
    # Public: change password                                              #
    # ------------------------------------------------------------------ #

    def change_password(
        self,
        vault_id: str,
        old_password: bytearray,
        new_password: bytearray,
    ) -> None:
        """Change the vault's encryption password."""
        if len(new_password) < 8:
            raise VaultError("New password must be at least 8 characters.")
        vault = self._registry.get(vault_id)
        if is_mounted(self._mountpoint_for(vault_id)):
            raise VaultError("Vault must be locked before changing its password.")
        try:
            self._backend.change_password(vault.path, old_password, new_password)
        except BackendError as exc:
            raise VaultError(str(exc)) from exc

    # ------------------------------------------------------------------ #
    # Public: rename / toggle stealth                                      #
    # ------------------------------------------------------------------ #

    def rename_vault(self, vault_id: str, new_name: str) -> None:
        if not new_name.strip():
            raise VaultError("Name cannot be empty.")
        vault = self._registry.get(vault_id)
        vault.name = new_name.strip()
        self._registry.update(vault)

    def set_stealth(self, vault_id: str, stealth: bool) -> None:
        """Toggle stealth mode.  Vault must be locked."""
        vault = self._registry.get(vault_id)
        if is_mounted(self._mountpoint_for(vault_id)):
            raise VaultError("Lock the vault before changing stealth mode.")

        old_path = Path(vault.path)
        parent = old_path.parent
        base = old_path.name.lstrip(".")
        new_name = f".{base}" if stealth else base
        new_path = parent / new_name

        if old_path != new_path:
            old_path.rename(new_path)
            vault.path = str(new_path)

        vault.stealth = stealth
        self._registry.update(vault)

    # ------------------------------------------------------------------ #
    # Public: delete                                                       #
    # ------------------------------------------------------------------ #

    def delete_vault(
        self,
        vault_id: str,
        delete_files: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        """
        Remove vault from registry and optionally delete files.

        *delete_files* is irreversible.  The vault must be locked.
        """
        vault = self._registry.get(vault_id)
        if is_mounted(self._mountpoint_for(vault_id)):
            raise VaultError("Lock the vault before deleting it.")

        self._registry.remove(vault_id)

        if delete_files:
            import shutil
            if on_progress:
                on_progress(f"Deleting vault files at {vault.path}…")
            shutil.rmtree(vault.path, ignore_errors=False)
            log.info("Deleted vault files at %s", vault.path)

    # ------------------------------------------------------------------ #
    # Public: backup config                                                #
    # ------------------------------------------------------------------ #

    def backup_vault_config(self, vault_id: str, dest_path: str) -> None:
        """Copy gocryptfs.conf to *dest_path* for backup."""
        import shutil
        vault = self._registry.get(vault_id)
        conf_src = Path(vault.path) / "gocryptfs.conf"
        if not conf_src.exists():
            raise VaultError("gocryptfs.conf not found.")
        shutil.copy2(str(conf_src), dest_path)
        os.chmod(dest_path, 0o600)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _mountpoint_for(self, vault_id: str) -> str:
        return os.path.join(self._runtime_dir, vault_id)

    def _recover_stale_mounts(self) -> None:
        """At startup, detect orphaned FUSE mounts and clean them up."""
        stale = find_stale_mounts(self._runtime_dir)
        for mp in stale:
            vault_id = os.path.basename(mp)
            log.warning("Stale mount detected: %s — cleaning up.", mp)
            success, msg = force_unmount(mp)
            if success:
                log.info("Cleaned stale mount %s", mp)
            else:
                log.error("Could not clean stale mount %s: %s", mp, msg)
