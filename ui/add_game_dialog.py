from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QRadioButton, QGroupBox,
    QFileDialog, QFrame,
)


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

        # Warning
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
        self._mode_files = QRadioButton("Multiple files  — the game saves specific files (select each one)")
        self._mode_folder = QRadioButton("Entire folder  — the game saves an entire folder, including subfolders")
        self._mode_file.setChecked(True)
        self._mode_file.toggled.connect(self._on_mode_changed)
        self._mode_files.toggled.connect(self._on_mode_changed)
        self._mode_folder.toggled.connect(self._on_mode_changed)
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
        self._path_edit.setPlaceholderText("Path to save file…")
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

    def _on_mode_changed(self) -> None:
        if self._mode_files.isChecked():
            self._path_edit.setPlaceholderText("Use 'Add files…' to select files, or type paths separated by ;")
            self._browse_btn.setText("Add files…")
            self._browse_btn.setFixedWidth(100)
        elif self._mode_file.isChecked():
            self._path_edit.setPlaceholderText("Path to save file…")
            self._browse_btn.setText("Browse…")
            self._browse_btn.setFixedWidth(90)
        else:
            self._path_edit.setPlaceholderText("Path to save folder…")
            self._browse_btn.setText("Browse…")
            self._browse_btn.setFixedWidth(90)

    def _on_browse(self) -> None:
        if self._mode_file.isChecked():
            path, _ = QFileDialog.getOpenFileName(
                self, "Select save file", self._path_edit.text() or ""
            )
            if path:
                self._path_edit.setText(path)
        elif self._mode_files.isChecked():
            paths, _ = QFileDialog.getOpenFileNames(
                self, "Select save files", ""
            )
            if paths:
                existing = [p.strip() for p in self._path_edit.text().split(";") if p.strip()]
                merged = existing + [p for p in paths if p not in existing]
                self._path_edit.setText("; ".join(merged))
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
