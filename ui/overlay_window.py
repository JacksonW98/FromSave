import sys
from typing import Callable, Optional

from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication, QLineEdit

_SLOT_ROWS = 5
_SLOT_RADIUS = _SLOT_ROWS // 2

_HOTKEYS_STYLE = "color: #6f6f80; font-size: 9px; background: transparent;"
_MESSAGE_STYLE = "color: #c9a8ff; font-size: 10px; font-weight: 600; background: transparent;"
_SLOT_STYLE = "color: #9393a2; font-size: 11px; background: transparent;"
_CURRENT_SLOT_STYLE = (
    "color: #ffffff; font-size: 12px; font-weight: 600; "
    "background: rgba(255,255,255,0.08); border-radius: 4px;"
)
_MESSAGE_DURATION_MS = 2500


def _slot_window(total: int, current_row: int, max_count: int = _SLOT_ROWS) -> range:
    """Slot indices centered on current_row, shifted inward at either end of the list."""
    if total <= 0:
        return range(0)
    start = max(0, current_row - _SLOT_RADIUS)
    end = min(total - 1, current_row + _SLOT_RADIUS)
    count = min(max_count, total)
    while (end - start + 1) < count:
        if start > 0:
            start -= 1
        elif end < total - 1:
            end += 1
        else:
            break
    return range(start, end + 1)


class OverlayWindow(QWidget):
    """Frameless, always-on-top status panel shown over the game.

    Draggable anywhere on its body; on_moved(x, y) is called after a drag.
    """

    def __init__(self, on_moved: Optional[Callable[[int, int], None]] = None, parent=None) -> None:
        super().__init__(parent)
        if sys.platform.startswith("linux"):
            # Many Linux window managers hide Tool windows when the app loses
            # focus, which would hide the overlay as soon as the game is focused.
            # A plain window that refuses focus avoids that (at the cost of a
            # possible taskbar entry).
            self.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.WindowDoesNotAcceptFocus
            )
        else:
            self.setWindowFlags(
                Qt.WindowType.Tool
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFixedSize(260, 222)
        self.setStyleSheet(
            "OverlayWindow { background: #17171d; border: 1px solid #3a3a46; border-radius: 8px; }"
        )

        self._on_moved = on_moved
        self._drag_offset = QPoint()
        self._dragging = False
        self._hotkeys_line = ""

        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self._clear_message)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self._game_lbl = QLabel("")
        self._game_lbl.setStyleSheet("color: #e8e8ee; font-size: 13px; font-weight: 600; background: transparent;")
        self._profile_lbl = QLabel("")
        self._profile_lbl.setStyleSheet("color: #a8a8b8; font-size: 11px; background: transparent;")

        layout.addWidget(self._game_lbl)
        layout.addWidget(self._profile_lbl)
        layout.addSpacing(6)

        self._slot_lbls: list[QLabel] = []
        for _ in range(_SLOT_ROWS):
            lbl = QLabel("")
            lbl.setContentsMargins(6, 2, 6, 2)
            layout.addWidget(lbl)
            self._slot_lbls.append(lbl)

        layout.addStretch()

        self._hotkeys_lbl = QLabel("")
        self._hotkeys_lbl.setStyleSheet(_HOTKEYS_STYLE)
        self._hotkeys_lbl.setWordWrap(True)
        layout.addWidget(self._hotkeys_lbl)

        self._rename_edit = QLineEdit()
        self._rename_edit.setPlaceholderText("New save name")
        self._rename_edit.setStyleSheet(
            "color: #e8e8ee; background: #25252e; border: 1px solid #626270; "
            "border-radius: 4px; padding: 4px 6px;"
        )
        self._rename_edit.setReadOnly(True)
        self._rename_edit.hide()
        layout.addWidget(self._rename_edit)

    def begin_rename(self, current_name: str) -> None:
        """Show the inline name editor in place of the hotkeys line."""
        self._hotkeys_lbl.hide()
        self._rename_edit.setText(current_name)
        self._rename_edit.show()
        self._rename_edit.selectAll()

    def set_rename_text(self, text: str) -> None:
        self._rename_edit.setText(text)

    def end_rename(self) -> None:
        self._rename_edit.hide()
        self._hotkeys_lbl.show()

    def set_opacity(self, value: float) -> None:
        self.setWindowOpacity(max(0.2, min(1.0, value)))

    def show_message(self, text: str, duration_ms: int = _MESSAGE_DURATION_MS) -> None:
        """Briefly show action feedback in place of the hotkeys line."""
        self._hotkeys_lbl.setText(text)
        self._hotkeys_lbl.setStyleSheet(_MESSAGE_STYLE)
        self._message_timer.start(duration_ms)

    def _clear_message(self) -> None:
        self._message_timer.stop()
        self._hotkeys_lbl.setText(self._hotkeys_line)
        self._hotkeys_lbl.setStyleSheet(_HOTKEYS_STYLE)

    def update_content(
        self, game: str, profile: str, slot_names: list[str], current_row: int,
        hotkeys_line: str = "",
    ) -> None:
        self._game_lbl.setText(game or "No game selected")
        self._profile_lbl.setText(profile)

        window = list(_slot_window(len(slot_names), current_row))
        for i, lbl in enumerate(self._slot_lbls):
            if i >= len(window):
                lbl.setText("")
                lbl.setStyleSheet("background: transparent;")
                continue
            idx = window[i]
            if idx == current_row:
                lbl.setText(f"▸ {slot_names[idx]}")
                lbl.setStyleSheet(_CURRENT_SLOT_STYLE)
            else:
                lbl.setText(f"   {slot_names[idx]}")
                lbl.setStyleSheet(_SLOT_STYLE)

        if not slot_names:
            self._slot_lbls[0].setText("No slot selected")
            self._slot_lbls[0].setStyleSheet(_SLOT_STYLE)

        self._hotkeys_line = hotkeys_line
        if not self._message_timer.isActive():
            self._hotkeys_lbl.setText(hotkeys_line)

    def show_at_saved_or_default(self, pos_x: int, pos_y: int) -> None:
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        if pos_x < 0 or pos_y < 0:
            top_left = available.topLeft() if available else QPoint(0, 0)
            self.move(top_left + QPoint(20, 20))
        else:
            point = QPoint(pos_x, pos_y)
            if available and not available.contains(point):
                point = available.topLeft() + QPoint(20, 20)
            self.move(point)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            if self._on_moved:
                self._on_moved(self.x(), self.y())
            event.accept()
