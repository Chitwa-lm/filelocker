"""Abstract base class for encryption backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BackendError(Exception):
    """Raised when a backend operation fails."""


class BackendAdapter(ABC):
    """
    Interface all encryption backends must implement.

    Password handling contract:
      - Passwords are passed as bytearray objects.
      - The backend zeroes the buffer as soon as it is no longer needed.
      - Passwords must NEVER appear in subprocess argv or log output.
    """

    @abstractmethod
    def init_vault(self, vault_path: str, password: bytearray,
                   master_key_hex: str | None = None) -> None:
        """
        Initialise a new vault at *vault_path*.

        If *master_key_hex* is provided it will be used as the initial
        master key (for recovery key support).

        Raises BackendError on failure.
        """

    @abstractmethod
    def mount(self, vault_path: str, mountpoint: str,
              password: bytearray) -> None:
        """
        Mount *vault_path* at *mountpoint*.

        Raises BackendError on wrong password or other failure.
        """

    @abstractmethod
    def unmount(self, mountpoint: str, force: bool = False) -> None:
        """
        Unmount *mountpoint*.

        If *force* is True, attempt a lazy unmount (-uz) even if files
        are open.

        Raises BackendError on failure.
        """

    @abstractmethod
    def change_password(self, vault_path: str,
                        old_password: bytearray,
                        new_password: bytearray) -> None:
        """
        Change the vault password.

        Raises BackendError on wrong old password or other failure.
        """

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """
        Check whether the backend binary is installed and usable.

        Returns (available: bool, message: str).
        """
