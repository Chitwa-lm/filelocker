"""
Vault registry — persists vault metadata to ~/.config/filelocker/vaults.json.

Security:
  - File is created/updated with mode 600 (owner read/write only).
  - Writes are atomic: write to a temp file then os.replace().
  - Passwords are never stored here.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Iterator

from .vault import Vault
from .utils import get_config_dir

log = logging.getLogger(__name__)

_REGISTRY_VERSION = 1


class Registry:
    """Thread-safe (GIL-protected) vault registry backed by a JSON file."""

    def __init__(self, config_dir: str | None = None) -> None:
        self._dir = Path(config_dir or get_config_dir())
        self._path = self._dir / "vaults.json"
        self._vaults: dict[str, Vault] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def add(self, vault: Vault) -> None:
        """Register a vault. Raises ValueError if id already exists."""
        if vault.id in self._vaults:
            raise ValueError(f"Vault id {vault.id!r} already registered.")
        self._vaults[vault.id] = vault
        self._save()

    def remove(self, vault_id: str) -> None:
        """Unregister a vault by id. Raises KeyError if not found."""
        if vault_id not in self._vaults:
            raise KeyError(f"Vault {vault_id!r} not found in registry.")
        del self._vaults[vault_id]
        self._save()

    def update(self, vault: Vault) -> None:
        """Persist updated vault metadata (name, stealth flag, etc.)."""
        if vault.id not in self._vaults:
            raise KeyError(f"Vault {vault.id!r} not found in registry.")
        self._vaults[vault.id] = vault
        self._save()

    def get(self, vault_id: str) -> Vault:
        """Retrieve a vault by id. Raises KeyError if not found."""
        if vault_id not in self._vaults:
            raise KeyError(f"Vault {vault_id!r} not found.")
        return self._vaults[vault_id]

    def all(self) -> list[Vault]:
        """Return all registered vaults (sorted by creation date)."""
        return sorted(self._vaults.values(), key=lambda v: v.created)

    def visible(self) -> list[Vault]:
        """Return non-stealth vaults."""
        return [v for v in self.all() if not v.stealth]

    def __iter__(self) -> Iterator[Vault]:
        return iter(self.all())

    def __len__(self) -> int:
        return len(self._vaults)

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        if not self._path.exists():
            log.debug("No registry file found at %s; starting empty.", self._path)
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if data.get("version") != _REGISTRY_VERSION:
                log.warning("Registry version mismatch; attempting to load anyway.")
            for entry in data.get("vaults", []):
                try:
                    v = Vault.from_dict(entry)
                    self._vaults[v.id] = v
                except (KeyError, TypeError) as exc:
                    log.error("Skipping malformed vault entry: %s — %s", entry, exc)
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Failed to load registry: %s", exc)

    def _save(self) -> None:
        data = {
            "version": _REGISTRY_VERSION,
            "vaults": [v.to_dict() for v in self.all()],
        }
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        # Atomic write: temp file in same directory, then replace
        try:
            fd, tmp_path = tempfile.mkstemp(dir=self._dir, prefix=".vaults_tmp_")
            try:
                os.write(fd, payload.encode("utf-8"))
            finally:
                os.close(fd)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self._path)
            os.chmod(self._path, 0o600)
        except OSError as exc:
            log.error("Failed to save registry: %s", exc)
            raise
