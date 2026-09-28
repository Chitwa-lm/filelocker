"""Recovery key display dialog — shown once at vault creation."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk


class RecoveryKeyDialog(Adw.Window):
    """
    Modal dialog that displays the 24-word recovery mnemonic.

    The user must check a confirmation checkbox before they can close it.
    The window cannot be dismissed with Escape until confirmed.
    """

    def __init__(self, parent: Gtk.Window, mnemonic: str) -> None:
        super().__init__(
            title="Save Your Recovery Key",
            modal=True,
            transient_for=parent,
            default_width=520,
            default_height=480,
            deletable=False,
        )
        self._confirmed = False
        self._build_ui(mnemonic)

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self, mnemonic: str) -> None:
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        # Header
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        toolbar.add_top_bar(header)

        # Scrollable content
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_margin_top(24)
        outer.set_margin_bottom(24)
        outer.set_margin_start(24)
        outer.set_margin_end(24)

        # Warning banner
        banner = Adw.Banner()
        banner.set_title("Write these 24 words down. You will not see them again.")
        banner.set_revealed(True)
        outer.append(banner)

        # Description
        desc = Gtk.Label(
            label=(
                "If you forget your password, this recovery key is the only way "
                "to access your vault. Store it somewhere safe and separate from "
                "your device."
            ),
            wrap=True,
            xalign=0.0,
        )
        desc.add_css_class("body")
        outer.append(desc)

        # Mnemonic display
        words = mnemonic.strip().split()
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        grid.add_css_class("card")
        grid.set_margin_top(4)

        # Display 6 columns × 4 rows
        for i, word in enumerate(words):
            col = i % 6
            row = i // 6
            cell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            num_label = Gtk.Label(label=f"{i+1:2}.")
            num_label.add_css_class("dim-label")
            num_label.add_css_class("caption")
            num_label.set_width_chars(3)
            num_label.set_xalign(1.0)

            word_label = Gtk.Label(label=word)
            word_label.add_css_class("monospace")
            word_label.set_selectable(True)
            word_label.set_xalign(0.0)

            cell.append(num_label)
            cell.append(word_label)
            cell.set_margin_start(8 if col == 0 else 0)
            cell.set_margin_end(8 if col == 5 else 0)
            cell.set_margin_top(4 if row == 0 else 0)
            cell.set_margin_bottom(4 if row == 3 else 0)
            grid.attach(cell, col, row, 1, 1)

        outer.append(grid)

        # Copy button
        copy_btn = Gtk.Button(label="Copy to Clipboard")
        copy_btn.add_css_class("flat")
        copy_btn.set_halign(Gtk.Align.CENTER)
        copy_btn.connect("clicked", self._on_copy, mnemonic)
        outer.append(copy_btn)

        # Confirmation checkbox
        confirm_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        confirm_box.set_halign(Gtk.Align.CENTER)
        self._check = Gtk.CheckButton(
            label="I have written down my recovery key and stored it safely."
        )
        confirm_box.append(self._check)
        outer.append(confirm_box)

        scroll.set_child(outer)
        toolbar.set_content(scroll)

        # Continue button (disabled until checkbox ticked)
        self._continue_btn = Gtk.Button(label="Continue")
        self._continue_btn.add_css_class("suggested-action")
        self._continue_btn.set_sensitive(False)
        self._continue_btn.set_margin_bottom(16)
        self._continue_btn.set_margin_start(24)
        self._continue_btn.set_margin_end(24)
        self._continue_btn.connect("clicked", self._on_continue)
        self._check.connect("toggled", self._on_check_toggled)

        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        btn_bar.set_halign(Gtk.Align.CENTER)
        btn_bar.append(self._continue_btn)
        toolbar.add_bottom_bar(btn_bar)

    def _on_check_toggled(self, check: Gtk.CheckButton) -> None:
        self._continue_btn.set_sensitive(check.get_active())

    def _on_copy(self, _btn: Gtk.Button, mnemonic: str) -> None:
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(mnemonic)

    def _on_continue(self, _btn: Gtk.Button) -> None:
        self._confirmed = True
        self.close()

    @property
    def confirmed(self) -> bool:
        return self._confirmed
