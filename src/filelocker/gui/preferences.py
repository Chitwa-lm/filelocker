"""Preferences dialog — idle timeout and display settings."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

# Timeout values in seconds; 0 = never
TIMEOUT_OPTIONS = [
    (60,    "1 minute"),
    (300,   "5 minutes"),
    (900,   "15 minutes"),
    (1800,  "30 minutes"),
    (0,     "Never"),
]

# Maps settings value -> Adw.ColorScheme and display index
THEME_OPTIONS = [
    ("system", Adw.ColorScheme.DEFAULT,      "System"),
    ("light",  Adw.ColorScheme.FORCE_LIGHT,  "Light"),
    ("dark",   Adw.ColorScheme.FORCE_DARK,   "Dark"),
]


def apply_color_scheme(style_manager: Adw.StyleManager, theme: str) -> None:
    """Apply a colour scheme by settings key ('system', 'light', 'dark')."""
    for key, scheme, _ in THEME_OPTIONS:
        if key == theme:
            style_manager.set_color_scheme(scheme)
            return
    # Default fallback
    style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)


class PreferencesDialog(Adw.PreferencesWindow):
    """App-wide preferences window."""

    __gtype_name__ = "FileLockerPreferences"

    def __init__(self, parent: Gtk.Window, settings: dict) -> None:
        super().__init__(
            transient_for=parent,
            modal=True,
            title="Preferences",
        )
        self._settings = settings
        self._build_ui()

    def _build_ui(self) -> None:
        page = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")
        self.add(page)

        # ---- Appearance group ----
        appearance_group = Adw.PreferencesGroup(title="Appearance")
        page.add(appearance_group)

        theme_row = Adw.ComboRow(
            title="Theme",
            subtitle="Choose light, dark, or follow the system setting",
        )
        model = Gtk.StringList()
        current_theme = self._settings.get("theme", "system")
        selected_idx = 0
        for i, (key, _scheme, label) in enumerate(THEME_OPTIONS):
            model.append(label)
            if key == current_theme:
                selected_idx = i
        theme_row.set_model(model)
        theme_row.set_selected(selected_idx)
        self._theme_combo = theme_row
        # Live preview as the user changes the combo
        theme_row.connect("notify::selected", self._on_theme_changed)
        appearance_group.add(theme_row)

        # ---- Auto-lock group ----
        lock_group = Adw.PreferencesGroup(
            title="Auto-Lock",
            description="Automatically lock vaults when the system is idle or the screen locks.",
        )
        page.add(lock_group)

        self._screen_lock_row = Adw.SwitchRow(
            title="Lock on Screen Lock",
            subtitle="Lock all vaults when the screen saver activates or the session locks",
        )
        self._screen_lock_row.set_active(self._settings.get("lock_on_screen_lock", True))
        lock_group.add(self._screen_lock_row)

        idle_row = Adw.ComboRow(title="Idle Timeout")
        model2 = Gtk.StringList()
        current_timeout = self._settings.get("idle_timeout_seconds", 300)
        selected = 1
        for i, (secs, label) in enumerate(TIMEOUT_OPTIONS):
            model2.append(label)
            if secs == current_timeout:
                selected = i
        idle_row.set_model(model2)
        idle_row.set_selected(selected)
        self._idle_combo = idle_row
        lock_group.add(idle_row)

        # ---- Vault display group ----
        display_group = Adw.PreferencesGroup(title="Vault Display")
        page.add(display_group)

        self._show_stealth_row = Adw.SwitchRow(
            title="Show Stealth Vaults",
            subtitle="Include hidden vaults in the vault list",
        )
        self._show_stealth_row.set_active(self._settings.get("show_stealth", False))
        display_group.add(self._show_stealth_row)

        self._show_paths_row = Adw.SwitchRow(
            title="Show Vault Paths",
            subtitle="Display the full storage path under each vault name",
        )
        self._show_paths_row.set_active(self._settings.get("show_paths", True))
        display_group.add(self._show_paths_row)

        self.connect("close-request", self._on_close)

    def _on_theme_changed(self, combo: Adw.ComboRow, _param) -> None:
        """Live-preview the selected theme without waiting for close."""
        idx = combo.get_selected()
        key = THEME_OPTIONS[idx][0]
        style_manager = Adw.StyleManager.get_default()
        apply_color_scheme(style_manager, key)

    def _on_close(self, _win) -> bool:
        idx = self._theme_combo.get_selected()
        self._settings["theme"] = THEME_OPTIONS[idx][0]
        timeout_idx = self._idle_combo.get_selected()
        self._settings["idle_timeout_seconds"] = TIMEOUT_OPTIONS[timeout_idx][0]
        self._settings["lock_on_screen_lock"] = self._screen_lock_row.get_active()
        self._settings["show_stealth"] = self._show_stealth_row.get_active()
        self._settings["show_paths"] = self._show_paths_row.get_active()
        return False
