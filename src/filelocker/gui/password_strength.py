"""Password strength meter widget."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject

from ..core.utils import score_password


class PasswordStrengthBar(Gtk.Box):
    """
    A composite widget that shows a coloured progress bar and a label
    indicating password strength.  Attach it below any password entry.
    """

    __gtype_name__ = "PasswordStrengthBar"

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_margin_top(4)

        self._bar = Gtk.LevelBar()
        self._bar.set_min_value(0)
        self._bar.set_max_value(4)
        self._bar.set_value(0)
        # Remove default offsets and add our own
        self._bar.remove_offset_value(Gtk.LEVEL_BAR_OFFSET_LOW)
        self._bar.remove_offset_value(Gtk.LEVEL_BAR_OFFSET_HIGH)
        self._bar.remove_offset_value(Gtk.LEVEL_BAR_OFFSET_FULL)
        self._bar.add_offset_value("strength-very-weak", 1)
        self._bar.add_offset_value("strength-weak", 2)
        self._bar.add_offset_value("strength-fair", 3)
        self._bar.add_offset_value("strength-strong", 4)

        self._label = Gtk.Label(label="", xalign=0.0)
        self._label.add_css_class("caption")
        self._label.add_css_class("dim-label")

        self.append(self._bar)
        self.append(self._label)

    def update(self, password: str) -> int:
        """
        Recalculate and display strength for *password*.
        Returns the score (0–4).
        """
        score, label = score_password(password)
        self._bar.set_value(score)
        self._label.set_text(label)

        # Colour via CSS classes
        for cls in ("error", "warning", "accent", "success"):
            self._bar.remove_css_class(cls)
        colour = ["error", "error", "warning", "accent", "success"][score]
        self._bar.add_css_class(colour)

        return score
