"""
Auto-lock manager.

Listens for:
  1. org.freedesktop.login1.Session  Lock signal  (generic systemd-logind)
  2. org.gnome.ScreenSaver            ActiveChanged signal (GNOME)

Also runs an idle-timeout countdown that fires a callback after N seconds
of no explicit "ping" calls.

Usage:
    def on_lock():
        vault_manager.lock_all(force=True)

    al = AutoLockManager(on_lock_callback=on_lock, idle_timeout_seconds=300)
    al.start()
    # ... in main loop ...
    al.ping()          # call this on any user activity
    al.stop()
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)

_DBUS_AVAILABLE = False
try:
    import dbus
    import dbus.mainloop.glib
    _DBUS_AVAILABLE = True
except ImportError:
    log.warning("dbus-python not available; screen-lock auto-lock disabled.")


class AutoLockManager:
    """
    Manages two auto-lock mechanisms: D-Bus session signals and idle timeout.

    Both run in a background thread so they never block the GTK main loop.
    The *on_lock_callback* is called from that thread; callers must use
    GLib.idle_add() if they need to update the UI.
    """

    def __init__(
        self,
        on_lock_callback: Callable[[], None],
        idle_timeout_seconds: int = 300,
        lock_on_screen_lock: bool = True,
    ) -> None:
        self._callback = on_lock_callback
        self._idle_timeout = idle_timeout_seconds
        self._lock_on_screen_lock = lock_on_screen_lock
        self._last_activity = time.monotonic()
        self._running = False
        self._thread: threading.Thread | None = None
        self._dbus_thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Start background monitoring."""
        self._running = True
        self._last_activity = time.monotonic()

        # Idle timer thread
        if self._idle_timeout > 0:
            self._thread = threading.Thread(
                target=self._idle_loop, daemon=True, name="filelocker-idle"
            )
            self._thread.start()
            log.debug("Idle timer started (%ds)", self._idle_timeout)

        # D-Bus listener thread
        if _DBUS_AVAILABLE and self._lock_on_screen_lock:
            self._dbus_thread = threading.Thread(
                target=self._dbus_loop, daemon=True, name="filelocker-dbus"
            )
            self._dbus_thread.start()
            log.debug("D-Bus lock listener started.")

    def stop(self) -> None:
        """Stop all monitoring threads."""
        self._running = False

    def ping(self) -> None:
        """Reset the idle countdown (call on any user interaction)."""
        self._last_activity = time.monotonic()

    def set_idle_timeout(self, seconds: int) -> None:
        """Update the idle timeout at runtime."""
        self._idle_timeout = seconds
        self.ping()

    def set_lock_on_screen_lock(self, enabled: bool) -> None:
        self._lock_on_screen_lock = enabled

    # ------------------------------------------------------------------ #
    # Idle loop                                                            #
    # ------------------------------------------------------------------ #

    def _idle_loop(self) -> None:
        while self._running:
            time.sleep(5)
            if not self._running:
                break
            if self._idle_timeout <= 0:
                continue
            elapsed = time.monotonic() - self._last_activity
            if elapsed >= self._idle_timeout:
                log.info("Idle timeout reached (%ds); locking all vaults.", self._idle_timeout)
                self._fire_lock()
                self._last_activity = time.monotonic()

    # ------------------------------------------------------------------ #
    # D-Bus loop                                                           #
    # ------------------------------------------------------------------ #

    def _dbus_loop(self) -> None:
        if not _DBUS_AVAILABLE:
            return
        try:
            from gi.repository import GLib
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SessionBus()

            # GNOME ScreenSaver
            try:
                bus.add_signal_receiver(
                    self._on_screensaver_active_changed,
                    signal_name="ActiveChanged",
                    dbus_interface="org.gnome.ScreenSaver",
                    path="/org/gnome/ScreenSaver",
                )
                log.debug("Listening for GNOME ScreenSaver.ActiveChanged")
            except Exception as exc:
                log.debug("GNOME ScreenSaver signal setup failed: %s", exc)

            # org.freedesktop.login1 Session Lock
            try:
                system_bus = dbus.SystemBus()
                system_bus.add_signal_receiver(
                    self._on_session_lock,
                    signal_name="Lock",
                    dbus_interface="org.freedesktop.login1.Session",
                )
                log.debug("Listening for login1 Session.Lock")
            except Exception as exc:
                log.debug("login1 Session.Lock signal setup failed: %s", exc)

            loop = GLib.MainLoop()
            # Run loop until stopped
            def check_running():
                if not self._running:
                    loop.quit()
                    return False
                return True

            GLib.timeout_add_seconds(2, check_running)
            loop.run()

        except Exception as exc:
            log.error("D-Bus auto-lock loop error: %s", exc)

    def _on_screensaver_active_changed(self, active: bool) -> None:
        if active:
            log.info("Screen saver activated; locking all vaults.")
            self._fire_lock()

    def _on_session_lock(self) -> None:
        log.info("Session locked; locking all vaults.")
        self._fire_lock()

    def _fire_lock(self) -> None:
        try:
            self._callback()
        except Exception as exc:
            log.error("Auto-lock callback error: %s", exc)
