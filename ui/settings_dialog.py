import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QLineEdit, QGridLayout, QGroupBox,
    QRadioButton, QFileDialog,
)

import config
import storage


class SettingsDialog(QDialog):
    def __init__(self, cfg: config.Config, games: list[storage.GameConfig], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self._cfg = config.Config(
            confirm_delete=cfg.confirm_delete,
            confirm_replace=cfg.confirm_replace,
            auto_name_imports=cfg.auto_name_imports,
            show_save_path=cfg.show_save_path,
        )
        self._games = games
        self._path_edits: dict[str, QLineEdit] = {}
        self._build_ui()
        ui_dir = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
        qss_path = os.path.join(ui_dir, "settings_dialog.qss")
        with open(qss_path, "r") as f:
            self.setStyleSheet(f.read().replace("{ui_dir}", ui_dir))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(16, 16, 16, 16)

        # Behaviour
        behaviour_box = QGroupBox("Behaviour")
        behaviour_layout = QVBoxLayout(behaviour_box)
        self._confirm_replace = QCheckBox("Confirm before replacing a save")
        self._confirm_replace.setChecked(self._cfg.confirm_replace)
        self._confirm_delete = QCheckBox("Confirm before deleting a save")
        self._confirm_delete.setChecked(self._cfg.confirm_delete)
        self._show_save_path = QCheckBox("Show save path in info panel")
        self._show_save_path.setChecked(self._cfg.show_save_path)
        behaviour_layout.addWidget(self._confirm_replace)
        behaviour_layout.addWidget(self._confirm_delete)
        behaviour_layout.addWidget(self._show_save_path)
        layout.addWidget(behaviour_box)

        # Import naming
        naming_box = QGroupBox("Import naming")
        naming_layout = QVBoxLayout(naming_box)
        naming_layout.setSpacing(10)
        self._prompt_name = QRadioButton("Always prompt for a name")
        self._auto_name = QRadioButton('Auto-name  (e.g. "new save", "new save 2"…)')
        if self._cfg.auto_name_imports:
            self._auto_name.setChecked(True)
        else:
            self._prompt_name.setChecked(True)
        naming_layout.addWidget(self._prompt_name)
        naming_layout.addWidget(self._auto_name)
        layout.addWidget(naming_box)

        # Game save paths
        paths_box = QGroupBox("Game save paths")
        paths_layout = QGridLayout(paths_box)
        paths_layout.setSpacing(8)
        paths_layout.setColumnStretch(1, 1)
        for i, game in enumerate(self._games):
            lbl = QLabel(game.name)
            lbl.setStyleSheet("background: transparent;")
            edit = QLineEdit(game.save_path)
            edit.setPlaceholderText("Full path to save file…")
            browse_btn = QPushButton("Browse…")
            browse_btn.setFixedWidth(90)
            browse_btn.clicked.connect(self._make_browse(edit))
            paths_layout.addWidget(lbl, i, 0, Qt.AlignVCenter)
            paths_layout.addWidget(edit, i, 1)
            paths_layout.addWidget(browse_btn, i, 2)
            self._path_edits[game.name] = edit
        layout.addWidget(paths_box)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _make_browse(self, edit: QLineEdit):
        def handler():
            path, _ = QFileDialog.getOpenFileName(
                self, "Select save file", edit.text() or ""
            )
            if path:
                edit.setText(path)
        return handler

    def _on_save(self) -> None:
        self._cfg.confirm_replace = self._confirm_replace.isChecked()
        self._cfg.confirm_delete = self._confirm_delete.isChecked()
        self._cfg.auto_name_imports = self._auto_name.isChecked()
        self._cfg.show_save_path = self._show_save_path.isChecked()
        self.accept()

    @property
    def result_config(self) -> config.Config:
        return self._cfg

    @property
    def result_paths(self) -> dict[str, str]:
        return {name: edit.text().strip() for name, edit in self._path_edits.items()}
