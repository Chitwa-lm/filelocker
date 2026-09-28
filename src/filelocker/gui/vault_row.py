"""
VaultRow — an AdwActionRow subclass representing a single vault in the list.

Emits custom signals consumed by the main window:
  vault-unlock-requested(vault_id: str)
  vault-lock-requested(vault_id: str)
  vault-open-requested(vault_id: str)
  vault-change-password-requested(vault_id: str)
  vault-backup-config-requested(vault_id: str)
  vault-delete-requested(vault_id: str)
  vault-toggle-stealth-requested(vault_id: str)
"""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GObject

from ..core.vault import Vault, VaultStatus

_STATUS_ICON = {
    VaultStatus.LOCKED:   ("lock-symbolic",          "dim-label"),
    VaultStatus.UNLOCKED: ("changes-allow-symbolic",  "success"),
    VaultStatus.BUSY:     ("dialog-warning-symbolic", "warning"),
    VaultStatus.ERROR:    ("dialog-error-symbolic",   "error"),
}

_STATUS_LABEL = {
    VaultStatus.LOCKED:   "Locked",
    VaultStatus.UNLOCKED: "Unlocked",
    VaultStatus.BUSY:     "Busy",
    VaultStatus.ERROR:    "Error",
}


class VaultRow(Adw.ActionRow):
    """One row in the vault list."""

    __gtype_name__ = "VaultRow"

    __gsignals__ = {
        "vault-unlock-requested":          (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "vault-lock-requested":            (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "vault-open-requested":            (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "vault-change-password-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "vault-backup-config-requested":   (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "vault-delete-requested":          (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "vault-toggle-stealth-requested":  (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, vault: Vault) -> None:
        super().__init__()
        self._vault = vault
        self._build()

    def _build(self) -> None:
        vault = self._vault

        self.set_title(vault.name)
        # Show mountpoint when unlocked, never the raw vault path
        if vault.status == VaultStatus.UNLOCKED and vault.mountpoint:
            self.set_subtitle(f"Unlocked — {vault.mountpoint}")
        else:
            self.set_subtitle("Locked")
        self.set_activatable(True)
        self.connect("activated", self._on_activated)

        # Status icon
        icon_name, css = _STATUS_ICON[vault.status]
        self._status_icon = Gtk.Image.new_from_icon_name(icon_name)
        self._status_icon.add_css_class(css)
        self.add_prefix(self._status_icon)

        # Status label
        self._status_label = Gtk.Label(label=_STATUS_LABEL[vault.status])
        self._status_label.add_css_class("caption")
        self._status_label.add_css_class("dim-label")
        self.add_suffix(self._status_label)

        # Action button (context menu trigger)
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("view-more-symbolic")
        menu_btn.add_css_class("flat")
        menu_btn.set_valign(Gtk.Align.CENTER)
        menu_btn.set_menu_model(self._build_menu(vault))
        self.add_suffix(menu_btn)

        # Lock/Unlock primary button
        self._action_btn = Gtk.Button()
        self._action_btn.set_valign(Gtk.Align.CENTER)
        self._update_action_button()
        self._action_btn.connect("clicked", self._on_action_btn_clicked)
        self.add_suffix(self._action_btn)

    def _build_menu(self, vault: Vault) -> Gio_Menu():
        from gi.repository import Gio
        menu = Gio.Menu()

        section1 = Gio.Menu()
        section1.append("Open Folder", f"row.open-{vault.id}")
        section1.append("Change Password", f"row.change-password-{vault.id}")
        section1.append("Backup Config", f"row.backup-config-{vault.id}")
        menu.append_section(None, section1)

        section2 = Gio.Menu()
        stealth_label = "Disable Stealth" if vault.stealth else "Enable Stealth"
        section2.append(stealth_label, f"row.toggle-stealth-{vault.id}")
        menu.append_section(None, section2)

        section3 = Gio.Menu()
        section3.append("Delete Vault…", f"row.delete-{vault.id}")
        menu.append_section(None, section3)

        # Register actions on the row widget
        ag = Gio.SimpleActionGroup()
        for action_name, signal_name in [
            (f"open-{vault.id}",            "vault-open-requested"),
            (f"change-password-{vault.id}", "vault-change-password-requested"),
            (f"backup-config-{vault.id}",   "vault-backup-config-requested"),
            (f"toggle-stealth-{vault.id}",  "vault-toggle-stealth-requested"),
            (f"delete-{vault.id}",          "vault-delete-requested"),
        ]:
            action = Gio.SimpleAction.new(action_name, None)
            _sig = signal_name  # capture
            _vid = vault.id
            action.connect("activate", lambda a, p, s=_sig, v=_vid: self.emit(s, v))
            ag.add_action(action)

        self.insert_action_group("row", ag)
        return menu

    def _update_action_button(self) -> None:
        status = self._vault.status
        if status == VaultStatus.UNLOCKED:
            self._action_btn.set_icon_name("system-lock-screen-symbolic")
            self._action_btn.set_tooltip_text("Lock vault")
            self._action_btn.add_css_class("flat")
            self._action_btn.remove_css_class("suggested-action")
        else:
            self._action_btn.set_icon_name("changes-prevent-symbolic")
            self._action_btn.set_tooltip_text("Unlock vault")
            self._action_btn.add_css_class("suggested-action")
            self._action_btn.remove_css_class("flat")

    def _on_activated(self, _row) -> None:
        """Clicking the row itself toggles lock/unlock."""
        self._on_action_btn_clicked(None)

    def _on_action_btn_clicked(self, _btn) -> None:
        if self._vault.status == VaultStatus.UNLOCKED:
            self.emit("vault-lock-requested", self._vault.id)
        else:
            self.emit("vault-unlock-requested", self._vault.id)

    def refresh(self, vault: Vault) -> None:
        """Update the row to reflect a changed vault state."""
        self._vault = vault
        # Update subtitle to show mountpoint when unlocked
        if vault.status == VaultStatus.UNLOCKED and vault.mountpoint:
            self.set_subtitle(f"Unlocked — {vault.mountpoint}")
        else:
            self.set_subtitle("Locked")
        icon_name, css = _STATUS_ICON[vault.status]
        self._status_icon.set_from_icon_name(icon_name)
        for cls in ("dim-label", "success", "warning", "error"):
            self._status_icon.remove_css_class(cls)
        self._status_icon.add_css_class(css)
        self._status_label.set_text(_STATUS_LABEL[vault.status])
        self._update_action_button()


def Gio_Menu():
    """Shim so the type hint resolves at runtime."""
    from gi.repository import Gio
    return Gio.Menu()
