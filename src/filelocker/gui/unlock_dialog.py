"""Password prompt dialog for unlocking a vault."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw


class UnlockDialog(Adw.MessageDialog):
    """
    Simple password prompt.

    Use run_async() with a callback to get the entered password.
    If the user cancels, the callback receives None.
    """

    __gtype_name__ = "UnlockDialog"

    def __init__(self, parent: Gtk.Window, vault_name: str) -> None:
        super().__init__(
            transient_for=parent,
            modal=True,
            heading=f"Unlock \u201c{vault_name}\u201d",
            body="Enter the vault password to decrypt and mount it.",
        )

        self._password: str | None = None

        # Password entry
        self._entry = Gtk.PasswordEntry()
        self._entry.set_show_peek_icon(True)
        self._entry.set_hexpand(True)
        self._entry.connect("activate", self._on_unlock_activated)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        box.append(self._entry)

        self._error_label = Gtk.Label(label="", xalign=0.0)
        self._error_label.add_css_class("error")
        self._error_label.add_css_class("caption")
        self._error_label.set_visible(False)
        box.append(self._error_label)

        self.set_extra_child(box)

        self.add_response("cancel", "Cancel")
        self.add_response("unlock", "Unlock")
        self.set_response_appearance("unlock", Adw.ResponseAppearance.SUGGESTED)
        self.set_default_response("unlock")
        self.set_close_response("cancel")
        self.connect("response", self._on_response)

    def show_error(self, message: str) -> None:
        """Display an error below the password field (e.g. wrong password)."""
        self._error_label.set_text(message)
        self._error_label.set_visible(True)
        self._entry.set_text("")
        self._entry.grab_focus()

    def _on_unlock_activated(self, _entry: Gtk.PasswordEntry) -> None:
        self.response("unlock")

    def _on_response(self, _dialog, response: str) -> None:
        if response == "unlock":
            self._password = self._entry.get_text()
        else:
            self._password = None

    @property
    def password(self) -> str | None:
        return self._password


class ChangePasswordDialog(Adw.Window):
    """Dialog for changing a vault's password."""

    __gtype_name__ = "ChangePasswordDialog"

    def __init__(self, parent: Gtk.Window, vault_name: str) -> None:
        super().__init__(
            title=f"Change Password — {vault_name}",
            modal=True,
            transient_for=parent,
            default_width=420,
            resizable=False,
        )
        self._result: tuple[str, str] | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)
        toolbar.add_top_bar(Adw.HeaderBar())

        clamp = Adw.Clamp(maximum_size=380)
        clamp.set_margin_top(16)
        clamp.set_margin_bottom(16)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        group = Adw.PreferencesGroup()
        self._old_pw = Adw.PasswordEntryRow(title="Current Password")
        self._new_pw = Adw.PasswordEntryRow(title="New Password")
        self._confirm_pw = Adw.PasswordEntryRow(title="Confirm New Password")
        group.add(self._old_pw)
        group.add(self._new_pw)
        group.add(self._confirm_pw)
        vbox.append(group)

        self._error_label = Gtk.Label(label="", xalign=0.0)
        self._error_label.add_css_class("error")
        self._error_label.add_css_class("caption")
        self._error_label.set_visible(False)
        vbox.append(self._error_label)

        clamp.set_child(vbox)
        toolbar.set_content(clamp)

        btn_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.END,
            margin_bottom=16,
            margin_end=16,
        )
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)

        save_btn = Gtk.Button(label="Change Password")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        btn_box.append(save_btn)

        toolbar.add_bottom_bar(btn_box)

    def _on_save(self, _btn) -> None:
        old = self._old_pw.get_text()
        new = self._new_pw.get_text()
        confirm = self._confirm_pw.get_text()

        if not old:
            self._show_error("Current password is required.")
            return
        if len(new) < 8:
            self._show_error("New password must be at least 8 characters.")
            return
        if new != confirm:
            self._show_error("New passwords do not match.")
            return

        self._result = (old, new)
        self.close()

    def _show_error(self, msg: str) -> None:
        self._error_label.set_text(msg)
        self._error_label.set_visible(True)

    @property
    def result(self) -> tuple[str, str] | None:
        return self._result
