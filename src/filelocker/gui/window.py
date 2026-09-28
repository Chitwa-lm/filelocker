"""
Main application window.

Layout:
  AdwApplicationWindow
    AdwToolbarView
      AdwHeaderBar          (top)
        [New Vault btn]  [Show Hidden toggle]  [Menu btn]
      AdwStatusPage         (empty state)  OR
      Gtk.ScrolledWindow
        AdwPreferencesGroup (vault list rows)
      AdwToolbarView bottom bar — status / error banner
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from typing import TYPE_CHECKING

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio

from ..core.vault import Vault, VaultStatus
from ..core.manager import VaultManager, VaultError
from ..core.utils import str_to_bytearray, zero_bytearray, is_mounted as is_mounted_path
from .vault_row import VaultRow
from .create_dialog import CreateVaultDialog
from .unlock_dialog import UnlockDialog, ChangePasswordDialog
from .recovery_dialog import RecoveryKeyDialog
from .preferences import PreferencesDialog

if TYPE_CHECKING:
    from .app import FileLockerApp

log = logging.getLogger(__name__)


class MainWindow(Adw.ApplicationWindow):
    """The primary application window."""

    def __init__(self, app: "FileLockerApp", manager: VaultManager) -> None:
        super().__init__(application=app, title="FileLocker")
        self.set_default_size(640, 480)
        self.set_size_request(480, 320)

        self._app = app
        self._manager = manager
        self._rows: dict[str, VaultRow] = {}
        self._show_stealth = False

        self._build_ui()
        self._refresh_vault_list()
        self._setup_actions()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        self._toolbar_view = Adw.ToolbarView()
        self.set_content(self._toolbar_view)

        # Header bar
        header = Adw.HeaderBar()

        new_btn = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="New Vault")
        new_btn.add_css_class("suggested-action")
        new_btn.connect("clicked", self._on_new_vault)
        header.pack_start(new_btn)

        # Show hidden toggle
        self._stealth_btn = Gtk.ToggleButton(
            icon_name="eye-open-negative-filled-symbolic",
            tooltip_text="Show hidden vaults",
            active=False,
        )
        self._stealth_btn.connect("toggled", self._on_stealth_toggled)
        header.pack_start(self._stealth_btn)

        # App menu
        menu_btn = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            tooltip_text="Menu",
            menu_model=self._build_app_menu(),
        )
        header.pack_end(menu_btn)

        self._toolbar_view.add_top_bar(header)

        # Error / info banner
        self._banner = Adw.Banner(title="")
        self._banner.set_revealed(False)
        self._banner.connect("button-clicked", lambda _: self._banner.set_revealed(False))
        self._banner.set_button_label("Dismiss")
        self._toolbar_view.add_top_bar(self._banner)

        # Main content stack
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        # Empty state
        self._empty_page = Adw.StatusPage(
            icon_name="locked-symbolic",
            title="No Vaults",
            description="Create your first vault to get started.",
        )
        create_btn = Gtk.Button(label="Create Vault")
        create_btn.add_css_class("suggested-action")
        create_btn.add_css_class("pill")
        create_btn.connect("clicked", self._on_new_vault)
        self._empty_page.set_child(create_btn)
        self._stack.add_named(self._empty_page, "empty")

        # Vault list
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._list_box_outer = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )

        self._vault_group = Adw.PreferencesGroup(title="Vaults")
        self._list_box_outer.append(self._vault_group)
        scroll.set_child(self._list_box_outer)
        self._stack.add_named(scroll, "list")

        self._toolbar_view.set_content(self._stack)

    def _build_app_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append("Preferences", "app.preferences")
        menu.append("Lock All Vaults", "app.lock-all")
        menu.append("About FileLocker", "app.about")
        return menu

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _setup_actions(self) -> None:
        app = self._app

        prefs_action = Gio.SimpleAction.new("preferences", None)
        prefs_action.connect("activate", self._on_preferences)
        app.add_action(prefs_action)

        lock_all_action = Gio.SimpleAction.new("lock-all", None)
        lock_all_action.connect("activate", self._on_lock_all)
        app.add_action(lock_all_action)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        app.add_action(about_action)

    # ------------------------------------------------------------------ #
    # Vault list management                                                #
    # ------------------------------------------------------------------ #

    def _refresh_vault_list(self) -> None:
        """Reload and redisplay all vaults from the manager."""
        vaults = self._manager.list_vaults(include_stealth=self._show_stealth)

        # Remove old rows
        for row in list(self._rows.values()):
            self._vault_group.remove(row)
        self._rows.clear()

        if not vaults:
            self._stack.set_visible_child_name("empty")
            return

        self._stack.set_visible_child_name("list")
        for vault in vaults:
            self._add_vault_row(vault)

    def _add_vault_row(self, vault: Vault) -> None:
        row = VaultRow(vault)
        row.connect("vault-unlock-requested", self._on_unlock_requested)
        row.connect("vault-lock-requested", self._on_lock_requested)
        row.connect("vault-open-requested", self._on_open_requested)
        row.connect("vault-change-password-requested", self._on_change_password_requested)
        row.connect("vault-backup-config-requested", self._on_backup_config_requested)
        row.connect("vault-delete-requested", self._on_delete_requested)
        row.connect("vault-toggle-stealth-requested", self._on_toggle_stealth_requested)
        self._vault_group.add(row)
        self._rows[vault.id] = row

    def _update_row(self, vault_id: str) -> None:
        """Refresh a single row's display without rebuilding the whole list."""
        try:
            vault = self._manager.get_vault(vault_id)
            # Re-sync status from mounts
            self._manager.list_vaults(include_stealth=True)
            vault = self._manager.get_vault(vault_id)
            if vault_id in self._rows:
                self._rows[vault_id].refresh(vault)
        except KeyError:
            self._refresh_vault_list()

    # ------------------------------------------------------------------ #
    # Banners / toasts                                                     #
    # ------------------------------------------------------------------ #

    def _show_banner(self, message: str, error: bool = False) -> None:
        self._banner.set_title(message)
        self._banner.set_revealed(True)
        if error:
            self._banner.add_css_class("error")
        else:
            self._banner.remove_css_class("error")
        # Auto-dismiss after 6s on success
        if not error:
            GLib.timeout_add_seconds(6, lambda: self._banner.set_revealed(False))

    def _show_toast(self, message: str) -> None:
        toast = Adw.Toast(title=message, timeout=3)
        self.add_toast(toast)

    # ------------------------------------------------------------------ #
    # Vault action handlers                                                #
    # ------------------------------------------------------------------ #

    def _on_new_vault(self, _widget=None) -> None:
        from ..core.utils import get_data_dir
        dialog = CreateVaultDialog(self, get_data_dir())
        dialog.connect("close-request", self._on_create_dialog_closed)
        dialog.present()

    def _on_create_dialog_closed(self, dialog: CreateVaultDialog) -> bool:
        result = dialog.result
        if not result:
            return False
        # Run in thread to avoid blocking UI during gocryptfs init
        threading.Thread(
            target=self._do_create_vault,
            args=(result,),
            daemon=True,
        ).start()
        return False

    def _do_create_vault(self, result: dict) -> None:
        pw_ba = str_to_bytearray(result["password"])
        try:
            vault, mnemonic = self._manager.create_vault(
                name=result["name"],
                password=pw_ba,
                location=result["location"],
                stealth=result["stealth"],
            )
            GLib.idle_add(self._after_create_vault, vault, mnemonic)
        except VaultError as exc:
            GLib.idle_add(self._show_banner, f"Failed to create vault: {exc}", True)
        finally:
            zero_bytearray(pw_ba)

    def _after_create_vault(self, vault: Vault, mnemonic: str) -> None:
        self._refresh_vault_list()
        rec_dialog = RecoveryKeyDialog(self, mnemonic)
        rec_dialog.present()
        # Clear mnemonic string from memory (best effort in Python)
        mnemonic = " ".join(["*" * 5] * 24)

    def _on_unlock_requested(self, _row, vault_id: str) -> None:
        try:
            vault = self._manager.get_vault(vault_id)
        except KeyError:
            return
        dialog = UnlockDialog(self, vault.name)
        dialog.connect("response", self._on_unlock_response, vault_id, dialog)
        dialog.present()

    def _on_unlock_response(
        self, _dialog, response: str, vault_id: str, dialog: UnlockDialog
    ) -> None:
        if response != "unlock":
            return
        pw = dialog.password
        if not pw:
            return
        pw_ba = str_to_bytearray(pw)
        threading.Thread(
            target=self._do_unlock,
            args=(vault_id, pw_ba, dialog),
            daemon=True,
        ).start()

    def _do_unlock(self, vault_id: str, pw_ba: bytearray, dialog: UnlockDialog) -> None:
        try:
            mountpoint = self._manager.unlock_vault(vault_id, pw_ba)
            GLib.idle_add(self._after_unlock, vault_id, mountpoint, dialog)
        except VaultError as exc:
            msg = str(exc)
            GLib.idle_add(dialog.show_error, msg)
        finally:
            zero_bytearray(pw_ba)

    def _after_unlock(self, vault_id: str, mountpoint: str, dialog: UnlockDialog) -> None:
        dialog.close()
        self._update_row(vault_id)
        self._show_toast("Vault unlocked")
        # Auto-open file manager
        try:
            subprocess.Popen(["xdg-open", mountpoint])
        except FileNotFoundError:
            pass

    def _on_lock_requested(self, _row, vault_id: str) -> None:
        threading.Thread(
            target=self._do_lock,
            args=(vault_id, False),
            daemon=True,
        ).start()

    def _do_lock(self, vault_id: str, force: bool) -> None:
        try:
            self._manager.lock_vault(vault_id, force=force)
            GLib.idle_add(self._after_lock, vault_id)
        except VaultError as exc:
            msg = str(exc)
            if "files are open" in msg:
                GLib.idle_add(self._prompt_force_lock, vault_id, msg)
            else:
                GLib.idle_add(self._show_banner, f"Lock failed: {msg}", True)

    def _after_lock(self, vault_id: str) -> None:
        self._update_row(vault_id)
        self._show_toast("Vault locked")

    def _prompt_force_lock(self, vault_id: str, msg: str) -> None:
        dlg = Adw.MessageDialog(
            transient_for=self,
            modal=True,
            heading="Files Are Open",
            body=f"{msg}\n\nForce-lock will close FUSE access immediately. Unsaved changes may be lost.",
        )
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("force", "Force Lock")
        dlg.set_response_appearance("force", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect(
            "response",
            lambda d, r: threading.Thread(
                target=self._do_lock, args=(vault_id, True), daemon=True
            ).start() if r == "force" else None,
        )
        dlg.present()

    def _on_open_requested(self, _row, vault_id: str) -> None:
        try:
            vault = self._manager.get_vault(vault_id)
        except KeyError:
            return
        mp = vault.mountpoint
        if mp and is_mounted_path(mp):
            subprocess.Popen(["xdg-open", mp])
        else:
            self._show_banner("Vault is locked. Unlock it first to open the folder.", error=True)

    def _on_change_password_requested(self, _row, vault_id: str) -> None:
        try:
            vault = self._manager.get_vault(vault_id)
        except KeyError:
            return
        dialog = ChangePasswordDialog(self, vault.name)
        dialog.connect("close-request", self._on_change_password_closed, vault_id, dialog)
        dialog.present()

    def _on_change_password_closed(
        self, dialog: ChangePasswordDialog, vault_id: str, d: ChangePasswordDialog
    ) -> bool:
        result = d.result
        if not result:
            return False
        old_ba = str_to_bytearray(result[0])
        new_ba = str_to_bytearray(result[1])
        threading.Thread(
            target=self._do_change_password,
            args=(vault_id, old_ba, new_ba),
            daemon=True,
        ).start()
        return False

    def _do_change_password(
        self, vault_id: str, old_ba: bytearray, new_ba: bytearray
    ) -> None:
        try:
            self._manager.change_password(vault_id, old_ba, new_ba)
            GLib.idle_add(self._show_toast, "Password changed successfully.")
        except VaultError as exc:
            GLib.idle_add(self._show_banner, f"Password change failed: {exc}", True)
        finally:
            zero_bytearray(old_ba)
            zero_bytearray(new_ba)

    def _on_backup_config_requested(self, _row, vault_id: str) -> None:
        file_dialog = Gtk.FileDialog(title="Save Config Backup", modal=True)
        file_dialog.save(self, None, self._on_backup_save_chosen, vault_id)

    def _on_backup_save_chosen(self, dialog, result, vault_id: str) -> None:
        try:
            file = dialog.save_finish(result)
            if file:
                dest = file.get_path()
                self._manager.backup_vault_config(vault_id, dest)
                self._show_toast(f"Config backup saved to {dest}")
        except Exception as exc:
            self._show_banner(f"Backup failed: {exc}", error=True)

    def _on_delete_requested(self, _row, vault_id: str) -> None:
        try:
            vault = self._manager.get_vault(vault_id)
        except KeyError:
            return
        dlg = Adw.MessageDialog(
            transient_for=self,
            modal=True,
            heading=f"Delete \u201c{vault.name}\u201d?",
            body=(
                "This will remove the vault from FileLocker's list.\n\n"
                "Do you also want to permanently delete the encrypted files? "
                "This cannot be undone."
            ),
        )
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("unregister", "Remove from List")
        dlg.add_response("delete-files", "Delete Files")
        dlg.set_response_appearance("delete-files", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", self._on_delete_response, vault_id)
        dlg.present()

    def _on_delete_response(self, _dlg, response: str, vault_id: str) -> None:
        if response == "cancel":
            return
        delete_files = response == "delete-files"
        try:
            self._manager.delete_vault(vault_id, delete_files=delete_files)
            self._refresh_vault_list()
            self._show_toast("Vault deleted." if delete_files else "Vault removed from list.")
        except VaultError as exc:
            self._show_banner(f"Delete failed: {exc}", error=True)

    def _on_toggle_stealth_requested(self, _row, vault_id: str) -> None:
        try:
            vault = self._manager.get_vault(vault_id)
            self._manager.set_stealth(vault_id, not vault.stealth)
            self._refresh_vault_list()
            label = "Hidden" if not vault.stealth else "Visible"
            self._show_toast(f"Vault is now {label}.")
        except VaultError as exc:
            self._show_banner(str(exc), error=True)

    # ------------------------------------------------------------------ #
    # Global actions                                                       #
    # ------------------------------------------------------------------ #

    def _on_stealth_toggled(self, btn: Gtk.ToggleButton) -> None:
        self._show_stealth = btn.get_active()
        self._refresh_vault_list()

    def _on_lock_all(self, _action=None, _param=None) -> None:
        errors = self._manager.lock_all(force=False)
        if errors:
            msgs = "; ".join(f"{vid}: {msg}" for vid, msg in errors)
            self._show_banner(f"Some vaults could not be locked: {msgs}", error=True)
        else:
            self._refresh_vault_list()
            self._show_toast("All vaults locked.")

    def _on_preferences(self, _action, _param) -> None:
        prefs = PreferencesDialog(self, self._app.settings)
        prefs.connect("close-request", self._on_preferences_closed)
        prefs.present()

    def _on_preferences_closed(self, _dlg) -> bool:
        # Apply changed settings to auto-lock manager
        self._app.apply_settings()
        return False

    def _on_about(self, _action, _param) -> None:
        about = Adw.AboutWindow(
            transient_for=self,
            application_name="FileLocker",
            application_icon="locked-symbolic",
            developer_name="FileLocker Contributors",
            version="1.0.0",
            website="https://github.com/filelocker/filelocker",
            issue_url="https://github.com/filelocker/filelocker/issues",
            license_type=Gtk.License.GPL_3_0,
            comments="Encrypted vault manager for Linux.",
            developers=["FileLocker Contributors"],
        )
        about.present()

    # ------------------------------------------------------------------ #
    # Public: called by auto-lock                                          #
    # ------------------------------------------------------------------ #

    def lock_all_from_autolock(self) -> None:
        """Called from the auto-lock thread via GLib.idle_add."""
        self._on_lock_all()
