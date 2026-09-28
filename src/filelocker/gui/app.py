"""
FileLockerApp — the Adw.Application subclass.

Entry point: FileLockerApp().run(sys.argv)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio

from ..core.manager import VaultManager
from ..core.autolock import AutoLockManager
from ..core.utils import get_config_dir

log = logging.getLogger(__name__)

_DEFAULT_SETTINGS = {
    "idle_timeout_seconds": 300,
    "lock_on_screen_lock": True,
    "show_stealth": False,
    "show_paths": True,
}

_SETTINGS_FILE = "settings.json"


class FileLockerApp(Adw.Application):
    """Main application class."""

    def __init__(self) -> None:
        super().__init__(
            application_id="io.github.filelocker",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._manager: VaultManager | None = None
        self._autolock: AutoLockManager | None = None
        self._window = None
        self.settings: dict = {}

        self.connect("activate", self._on_activate)
        self.connect("shutdown", self._on_shutdown)

        # Handle SIGTERM / SIGINT gracefully
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._on_signal)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._on_signal)

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def _on_activate(self, app: Adw.Application) -> None:
        self._load_settings()
        self._manager = VaultManager()
        self._start_autolock()

        from .window import MainWindow
        self._window = MainWindow(self, self._manager)
        self._window.present()

    def _on_shutdown(self, _app) -> None:
        log.info("App shutting down; locking all vaults.")
        if self._autolock:
            self._autolock.stop()
        if self._manager:
            self._manager.lock_all(force=True)

    def _on_signal(self) -> bool:
        log.info("Signal received; quitting.")
        self.quit()
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------ #
    # Settings                                                             #
    # ------------------------------------------------------------------ #

    def _settings_path(self) -> Path:
        return Path(get_config_dir()) / _SETTINGS_FILE

    def _load_settings(self) -> None:
        self.settings = dict(_DEFAULT_SETTINGS)
        path = self._settings_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.settings.update(data)
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Could not load settings: %s", exc)

    def save_settings(self) -> None:
        path = self._settings_path()
        try:
            path.write_text(
                json.dumps(self.settings, indent=2),
                encoding="utf-8",
            )
            os.chmod(path, 0o600)
        except OSError as exc:
            log.error("Could not save settings: %s", exc)

    def apply_settings(self) -> None:
        """Push updated settings to the auto-lock manager."""
        self.save_settings()
        if self._autolock:
            self._autolock.set_idle_timeout(
                self.settings.get("idle_timeout_seconds", 300)
            )
            self._autolock.set_lock_on_screen_lock(
                self.settings.get("lock_on_screen_lock", True)
            )
        # Refresh vault list if stealth visibility changed
        if self._window:
            self._window._show_stealth = self.settings.get("show_stealth", False)
            self._window._stealth_btn.set_active(self._window._show_stealth)
            self._window._refresh_vault_list()

    # ------------------------------------------------------------------ #
    # Auto-lock                                                            #
    # ------------------------------------------------------------------ #

    def _start_autolock(self) -> None:
        def _lock_callback():
            if self._window:
                GLib.idle_add(self._window.lock_all_from_autolock)

        self._autolock = AutoLockManager(
            on_lock_callback=_lock_callback,
            idle_timeout_seconds=self.settings.get("idle_timeout_seconds", 300),
            lock_on_screen_lock=self.settings.get("lock_on_screen_lock", True),
        )
        self._autolock.start()

    # ------------------------------------------------------------------ #
    # Public: ping idle timer on user activity                             #
    # ------------------------------------------------------------------ #

    def ping_idle(self) -> None:
        if self._autolock:
            self._autolock.ping()


def main() -> int:
    """Application entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s [%(name)s] %(message)s",
    )
    app = FileLockerApp()
    return app.run(sys.argv)
