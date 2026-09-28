"""New vault creation dialog."""

from __future__ import annotations

import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from .password_strength import PasswordStrengthBar


class CreateVaultDialog(Adw.Window):
    """
    Dialog for creating a new vault.

    Emits the 'vault-create-requested' signal with
    (name: str, password: str, location: str, stealth: bool)
    when the user clicks Create.
    """

    __gtype_name__ = "CreateVaultDialog"

    def __init__(self, parent: Gtk.Window, default_location: str) -> None:
        super().__init__(
            title="New Vault",
            modal=True,
            transient_for=parent,
            default_width=460,
            resizable=False,
        )
        self._default_location = default_location
        self._result: dict | None = None
        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        # Main content
        clamp = Adw.Clamp(maximum_size=400)
        clamp.set_margin_top(16)
        clamp.set_margin_bottom(16)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)

        # ---- Vault name ----
        name_group = Adw.PreferencesGroup(title="Vault Name")
        self._name_entry = Adw.EntryRow(title="Name")
        self._name_entry.connect("changed", self._validate)
        name_group.add(self._name_entry)
        vbox.append(name_group)

        # ---- Location ----
        loc_group = Adw.PreferencesGroup(title="Location")
        self._loc_row = Adw.ActionRow(
            title="Storage Location",
            subtitle=self._default_location,
            activatable=True,
        )
        self._loc_row.connect("activated", self._on_choose_location)
        loc_icon = Gtk.Image.new_from_icon_name("folder-symbolic")
        self._loc_row.add_suffix(loc_icon)
        loc_group.add(self._loc_row)
        vbox.append(loc_group)

        # ---- Password ----
        pw_group = Adw.PreferencesGroup(title="Password")

        self._pw_entry = Adw.PasswordEntryRow(title="Password")
        self._pw_entry.connect("changed", self._on_password_changed)
        pw_group.add(self._pw_entry)

        self._pw_confirm = Adw.PasswordEntryRow(title="Confirm Password")
        self._pw_confirm.connect("changed", self._validate)
        pw_group.add(self._pw_confirm)

        self._strength_bar = PasswordStrengthBar()
        pw_group.add(self._strength_bar)

        vbox.append(pw_group)

        # ---- Options ----
        opt_group = Adw.PreferencesGroup(title="Options")
        self._stealth_row = Adw.SwitchRow(
            title="Stealth Mode",
            subtitle="Hide this vault from the main list by default",
        )
        opt_group.add(self._stealth_row)
        vbox.append(opt_group)

        # ---- Error label ----
        self._error_label = Gtk.Label(label="", xalign=0.0)
        self._error_label.add_css_class("error")
        self._error_label.add_css_class("caption")
        self._error_label.set_visible(False)
        vbox.append(self._error_label)

        clamp.set_child(vbox)
        toolbar.set_content(clamp)

        # ---- Buttons ----
        btn_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.END,
            margin_top=8,
            margin_bottom=16,
            margin_end=16,
        )

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)

        self._create_btn = Gtk.Button(label="Create Vault")
        self._create_btn.add_css_class("suggested-action")
        self._create_btn.set_sensitive(False)
        self._create_btn.connect("clicked", self._on_create)
        btn_box.append(self._create_btn)

        toolbar.add_bottom_bar(btn_box)

    # ------------------------------------------------------------------ #
    # Callbacks                                                            #
    # ------------------------------------------------------------------ #

    def _on_password_changed(self, entry: Adw.PasswordEntryRow) -> None:
        self._strength_bar.update(entry.get_text())
        self._validate(entry)

    def _validate(self, _widget=None) -> None:
        name = self._name_entry.get_text().strip()
        pw = self._pw_entry.get_text()
        pw2 = self._pw_confirm.get_text()

        ok = True
        msg = ""

        if not name:
            ok = False
            msg = "Vault name is required."
        elif len(pw) < 8:
            ok = False
            msg = "Password must be at least 8 characters."
        elif pw != pw2:
            ok = False
            msg = "Passwords do not match."

        self._error_label.set_text(msg)
        self._error_label.set_visible(bool(msg))
        self._create_btn.set_sensitive(ok)

    def _on_choose_location(self, _row) -> None:
        dialog = Gtk.FileDialog(
            title="Choose Vault Storage Location",
            modal=True,
            initial_folder=Gio_file_for_path(self._default_location),
        )
        dialog.select_folder(self, None, self._on_location_chosen)

    def _on_location_chosen(self, dialog, result) -> None:
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                path = folder.get_path()
                self._default_location = path
                self._loc_row.set_subtitle(path)
        except Exception:
            pass

    def _on_create(self, _btn) -> None:
        self._result = {
            "name": self._name_entry.get_text().strip(),
            "password": self._pw_entry.get_text(),
            "location": self._default_location,
            "stealth": self._stealth_row.get_active(),
        }
        self.close()

    # ------------------------------------------------------------------ #
    # Result accessor                                                      #
    # ------------------------------------------------------------------ #

    @property
    def result(self) -> dict | None:
        """Returns the collected form data or None if cancelled."""
        return self._result


def Gio_file_for_path(path: str):
    """Helper to create a Gio.File from a path string."""
    from gi.repository import Gio
    return Gio.File.new_for_path(path)
