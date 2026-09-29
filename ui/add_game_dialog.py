from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from ui.save_path_widgets import SaveModeGroup, browse_save_path, set_path_input_mode


class AddGameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add game")
        self.setMinimumWidth(420)
        self._result: tuple[str, str, str] | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(16, 16, 16, 16)

        warning = QLabel(
            "⚠  FromSave has only been tested with a small number of games. "
            "It may not work correctly with every title — use at your own risk and always "
            "keep backups of any save files you care about."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #aa8833; font-size: 12px;")
        layout.addWidget(warning)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: #2a2a3a;")
        layout.addWidget(divider)

        name_lbl = QLabel("Game name")
        name_lbl.setObjectName("fieldLabel")
        layout.addWidget(name_lbl)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Bloodborne (maybe some day...)")
        layout.addWidget(self._name_edit)

        self._mode_group = SaveModeGroup()
        layout.addWidget(self._mode_group)

        path_lbl = QLabel("Save path")
        path_lbl.setObjectName("fieldLabel")
        layout.addWidget(path_lbl)
        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        browse_btn = QPushButton()
        browse_btn.clicked.connect(
            lambda: browse_save_path(self, self._path_edit, self._mode_group.mode())
        )
        set_path_input_mode(self._path_edit, browse_btn, "file")
        self._mode_group.mode_changed.connect(
            lambda mode: set_path_input_mode(self._path_edit, browse_btn, mode)
        )
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        add_btn = QPushButton("Add")
        add_btn.setObjectName("primaryBtn")
        add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(add_btn)
        layout.addLayout(btn_row)

    def _on_add(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setFocus()
            return
        self._result = (name, self._mode_group.mode(), self._path_edit.text().strip())
        self.accept()

    @property
    def result(self) -> tuple[str, str, str] | None:
        """(name, save mode, path text); "files" mode paths are "; "-separated."""
        return self._result
