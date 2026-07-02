from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QRadioButton, QGroupBox,
)
from PySide6.QtCore import Qt


class ConfigureGameDialog(QDialog):
    def __init__(self, game_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Set up {game_name}")
        self.setMinimumWidth(420)
        self._game_name = game_name
        self._result_mode: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(16, 16, 16, 16)

        intro = QLabel(
            f"A saves folder for <b>{self._game_name}</b> was found but it hasn't been "
            "configured yet. Select the save type below, then set the save path in "
            "<b>Settings</b>."
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.RichText)
        layout.addWidget(intro)

        mode_box = QGroupBox("Save type")
        mode_layout = QVBoxLayout(mode_box)
        mode_layout.setSpacing(8)
        self._mode_file = QRadioButton("Single file  — the game saves to one file (e.g. ER0000.sl2)")
        self._mode_files = QRadioButton("Multiple files  — the game saves specific files (select each one)")
        self._mode_folder = QRadioButton("Entire folder  — the game saves an entire folder, including subfolders")
        self._mode_file.setChecked(True)
        mode_layout.addWidget(self._mode_file)
        mode_layout.addWidget(self._mode_files)
        mode_layout.addWidget(self._mode_folder)
        layout.addWidget(mode_box)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        skip_btn = QPushButton("Skip for now")
        skip_btn.clicked.connect(self.reject)
        configure_btn = QPushButton("Configure")
        configure_btn.setObjectName("primaryBtn")
        configure_btn.clicked.connect(self._on_configure)
        btn_row.addWidget(skip_btn)
        btn_row.addWidget(configure_btn)
        layout.addLayout(btn_row)

    def _on_configure(self) -> None:
        if self._mode_file.isChecked():
            self._result_mode = "file"
        elif self._mode_files.isChecked():
            self._result_mode = "files"
        else:
            self._result_mode = "folder"
        self.accept()

    @property
    def result_mode(self) -> str | None:
        return self._result_mode
