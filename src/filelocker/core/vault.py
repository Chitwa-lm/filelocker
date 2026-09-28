"""Vault dataclass and status enum."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone


class VaultStatus(enum.Enum):
    LOCKED = "locked"
    UNLOCKED = "unlocked"
    BUSY = "busy"          # mounted but files held open
    ERROR = "error"        # stale mount / config missing


@dataclass
class Vault:
    """Represents a single registered vault."""

    id: str                        # 8-char hex, unique
    name: str                      # human-readable label
    path: str                      # absolute path to the encrypted directory
    stealth: bool = False          # hidden from list by default
    created: str = field(         # ISO-8601 UTC timestamp
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ------------------------------------------------------------------ #
    # Runtime-only fields (never persisted)                               #
    # ------------------------------------------------------------------ #
    _status: VaultStatus = field(
        default=VaultStatus.LOCKED, init=False, repr=False, compare=False
    )
    _mountpoint: str | None = field(
        default=None, init=False, repr=False, compare=False
    )

    # ------------------------------------------------------------------ #
    # Properties                                                          #
    # ------------------------------------------------------------------ #
    @property
    def status(self) -> VaultStatus:
        return self._status

    @status.setter
    def status(self, value: VaultStatus) -> None:
        self._status = value

    @property
    def mountpoint(self) -> str | None:
        return self._mountpoint

    @mountpoint.setter
    def mountpoint(self, value: str | None) -> None:
        self._mountpoint = value

    # ------------------------------------------------------------------ #
    # Serialisation helpers                                               #
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "stealth": self.stealth,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Vault":
        return cls(
            id=data["id"],
            name=data["name"],
            path=data["path"],
            stealth=data.get("stealth", False),
            created=data.get("created", datetime.now(timezone.utc).isoformat()),
        )
