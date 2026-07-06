from typing import Callable, Optional

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication


class OverlayWindow(QWidget):
    """A small, frameless, always-on-top, semi-transparent status panel shown
    over a game. Draggable anywhere on its body; reports its new position via
    on_moved so the caller can persist it."""

    def __init__(self, on_moved: Optional[Callable[[int, int], None]] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFixedSize(260, 152)
        self.setStyleSheet(
            "OverlayWindow { background: #17171d; border: 1px solid #3a3a46; border-radius: 8px; }"
        )

        self._on_moved = on_moved
        self._drag_offset = QPoint()
        self._dragging = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self._game_lbl = QLabel("")
        self._game_lbl.setStyleSheet("color: #e8e8ee; font-size: 13px; font-weight: 600; background: transparent;")
        self._profile_lbl = QLabel("")
        self._profile_lbl.setStyleSheet("color: #a8a8b8; font-size: 11px; background: transparent;")
        self._current_lbl = QLabel("")
        self._current_lbl.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 600; background: transparent;")
        self._neighbors_lbl = QLabel("")
        self._neighbors_lbl.setStyleSheet("color: #888899; font-size: 11px; background: transparent;")
        self._neighbors_lbl.setWordWrap(True)
        self._hotkeys_lbl = QLabel("")
        self._hotkeys_lbl.setStyleSheet("color: #6f6f80; font-size: 9px; background: transparent;")
        self._hotkeys_lbl.setWordWrap(True)

        layout.addWidget(self._game_lbl)
        layout.addWidget(self._profile_lbl)
        layout.addSpacing(6)
        layout.addWidget(self._current_lbl)
        layout.addWidget(self._neighbors_lbl)
        layout.addStretch()
        layout.addWidget(self._hotkeys_lbl)

    def set_opacity(self, value: float) -> None:
        self.setWindowOpacity(max(0.2, min(1.0, value)))

    def update_content(
        self, game: str, profile: str, current: str, prev_name: str, next_name: str,
        hotkeys_line: str = "",
    ) -> None:
        self._game_lbl.setText(game or "No game selected")
        self._profile_lbl.setText(profile)
        self._current_lbl.setText(current or "No slot selected")
        parts = []
        if prev_name:
            parts.append(f"◀ {prev_name}")
        if next_name:
            parts.append(f"{next_name} ▶")
        self._neighbors_lbl.setText("   ".join(parts))
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
