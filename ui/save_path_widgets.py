"""Widgets shared by the dialogs that configure a game's save location."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QLineEdit, QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

_MODE_DESCRIPTIONS = {
    "file": "Single file  — the game saves to one file (e.g. ER0000.sl2)",
    "files": "Multiple files  — the game saves specific files (select each one)",
    "folder": "Entire folder  — the game saves an entire folder, including subfolders",
}


class SaveModeGroup(QGroupBox):
    """Radio buttons for choosing a save mode: "file", "files" or "folder"."""

    mode_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__("Save type", parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        self._buttons: dict[str, QRadioButton] = {}
        for mode, text in _MODE_DESCRIPTIONS.items():
            btn = QRadioButton(text)
            btn.toggled.connect(lambda checked, m=mode: checked and self.mode_changed.emit(m))
            layout.addWidget(btn)
            self._buttons[mode] = btn
        self._buttons["file"].setChecked(True)

    def mode(self) -> str:
        return next(m for m, btn in self._buttons.items() if btn.isChecked())


def split_paths(text: str) -> list[str]:
    """Split a "; "-separated list of paths, as typed in "files" mode."""
    return [p.strip() for p in text.split(";") if p.strip()]


def set_path_input_mode(edit: QLineEdit, browse_btn: QPushButton, mode: str) -> None:
    if mode == "files":
        edit.setPlaceholderText("Paths separated by  ;  — use 'Add files…' to browse")
        browse_btn.setText("Add files…")
        browse_btn.setFixedWidth(100)
    else:
        edit.setPlaceholderText("Path to save file…" if mode == "file" else "Path to save folder…")
        browse_btn.setText("Browse…")
        browse_btn.setFixedWidth(90)


def browse_save_path(parent: QWidget, edit: QLineEdit, mode: str) -> None:
    """Show the file/folder picker for mode and put the result in edit."""
    if mode == "file":
        path, _ = QFileDialog.getOpenFileName(parent, "Select save file", edit.text())
        if path:
            edit.setText(path)
    elif mode == "files":
        paths, _ = QFileDialog.getOpenFileNames(parent, "Select save files", "")
        if paths:
            existing = split_paths(edit.text())
            edit.setText("; ".join(existing + [p for p in paths if p not in existing]))
    else:
        path = QFileDialog.getExistingDirectory(parent, "Select save folder", edit.text())
        if path:
            edit.setText(path)
