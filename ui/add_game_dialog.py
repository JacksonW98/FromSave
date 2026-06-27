from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QRadioButton, QGroupBox,
    QFileDialog,
)

import storage


class AddGameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add game")
        self.setMinimumWidth(420)
        self._result: tuple[str, str, str] | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(16, 16, 16, 16)

        # Name
        name_lbl = QLabel("Game name")
        name_lbl.setObjectName("fieldLabel")
        layout.addWidget(name_lbl)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Bloodborne (maybe some day...)")
        layout.addWidget(self._name_edit)

        # Save mode
        mode_box = QGroupBox("Save type")
        mode_layout = QVBoxLayout(mode_box)
        mode_layout.setSpacing(8)
        self._mode_file = QRadioButton("Single file  — the game saves to one file (e.g. ER0000.sl2)")
        self._mode_files = QRadioButton("Multiple files  — the game saves multiple files into a folder")
        self._mode_folder = QRadioButton("Entire folder  — the game saves an entire folder, including subfolders")
        self._mode_file.setChecked(True)
        mode_layout.addWidget(self._mode_file)
        mode_layout.addWidget(self._mode_files)
        mode_layout.addWidget(self._mode_folder)
        layout.addWidget(mode_box)

        # Path
        path_lbl = QLabel("Save path")
        path_lbl.setObjectName("fieldLabel")
        layout.addWidget(path_lbl)
        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Path to save file or folder…")
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.setFixedWidth(90)
        self._browse_btn.clicked.connect(self._on_browse)
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(self._browse_btn)
        layout.addLayout(path_row)

        # Buttons
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

    def _on_browse(self) -> None:
        if self._mode_file.isChecked():
            path, _ = QFileDialog.getOpenFileName(
                self, "Select save file", self._path_edit.text() or ""
            )
        else:
            path = QFileDialog.getExistingDirectory(
                self, "Select save folder", self._path_edit.text() or ""
            )
        if path:
            self._path_edit.setText(path)

    def _on_add(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setFocus()
            return
        if self._mode_file.isChecked():
            mode = "file"
        elif self._mode_files.isChecked():
            mode = "files"
        else:
            mode = "folder"
        self._result = (name, mode, self._path_edit.text().strip())
        self.accept()

    @property
    def result(self) -> tuple[str, str, str] | None:
        return self._result
