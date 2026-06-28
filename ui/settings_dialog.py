import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QLineEdit, QGroupBox, QWidget,
    QRadioButton, QFileDialog, QMessageBox, QKeySequenceEdit, QScrollArea,
)

import config
import storage
from ui.add_game_dialog import AddGameDialog


class SettingsDialog(QDialog):
    def __init__(self, cfg: config.Config, games: list[storage.GameConfig], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self.setMaximumHeight(700)
        self._cfg = config.Config(
            confirm_delete=cfg.confirm_delete,
            confirm_replace=cfg.confirm_replace,
            auto_name_imports=cfg.auto_name_imports,
            show_save_path=cfg.show_save_path,
            hotkey_import=cfg.hotkey_import,
            hotkey_load=cfg.hotkey_load,
            hotkey_ro_toggle=cfg.hotkey_ro_toggle,
        )
        self._game_entries: list[dict] = []
        self._build_ui()
        for game in games:
            self._add_game_row(game.name, game.save_mode, game.save_path, game.save_paths)
        ui_dir = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
        qss_path = os.path.join(ui_dir, "settings_dialog.qss")
        with open(qss_path, "r") as f:
            self.setStyleSheet(f.read().replace("{ui_dir}", ui_dir))

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll, 1)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setSpacing(14)
        layout.setContentsMargins(16, 16, 16, 12)

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

        # Hotkeys
        hotkeys_box = QGroupBox("Hotkeys")
        hotkeys_layout = QVBoxLayout(hotkeys_box)
        hotkeys_layout.setSpacing(6)

        self._hk_import = self._make_hotkey_row(hotkeys_layout, "Import save", self._cfg.hotkey_import)
        self._hk_load = self._make_hotkey_row(hotkeys_layout, "Load save", self._cfg.hotkey_load)
        self._hk_ro = self._make_hotkey_row(hotkeys_layout, "Toggle read-only", self._cfg.hotkey_ro_toggle)
        layout.addWidget(hotkeys_box)

        # Game save paths
        paths_box = QGroupBox("Game save paths")
        paths_outer = QVBoxLayout(paths_box)
        paths_outer.setSpacing(6)

        self._paths_layout = QVBoxLayout()
        self._paths_layout.setSpacing(4)
        paths_outer.addLayout(self._paths_layout)

        add_btn = QPushButton("+ Add game")
        add_btn.setObjectName("ghostBtn")
        add_btn.setFixedWidth(110)
        add_btn.clicked.connect(self._on_add_game)
        paths_outer.addWidget(add_btn, alignment=Qt.AlignLeft)

        layout.addWidget(paths_box)
        layout.addStretch()

        # Buttons — outside the scroll area so they're always visible
        from PySide6.QtWidgets import QFrame
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: #2a2a32; border: none;")
        outer.addWidget(divider)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 10, 16, 12)
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        outer.addLayout(btn_row)

    def _make_hotkey_row(self, parent_layout: QVBoxLayout, label: str, current: str) -> QKeySequenceEdit:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(130)
        row_layout.addWidget(lbl)

        editor = QKeySequenceEdit(QKeySequence(current))
        editor.setMaximumWidth(160)
        row_layout.addWidget(editor)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(60)
        clear_btn.setObjectName("ghostBtn")
        clear_btn.clicked.connect(editor.clear)
        row_layout.addWidget(clear_btn)

        row_layout.addStretch()
        parent_layout.addWidget(row)
        return editor

    def _add_game_row(self, name: str, mode: str, path: str = "", save_paths: list[str] | None = None) -> None:
        entry: dict = {"name": name, "mode": mode}

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(8)

        lbl = QLabel(name)
        lbl.setFixedWidth(160)
        mode_labels = {"file": "file", "files": "files", "folder": "folder"}
        lbl.setToolTip(f"Save type: {mode_labels.get(mode, mode)}")

        if mode == "files":
            initial_text = "; ".join(save_paths) if save_paths else path
            edit = QLineEdit(initial_text)
            edit.setPlaceholderText("Paths separated by  ;  — use 'Add files…' to browse")
            browse_btn = QPushButton("Add files…")
            browse_btn.setFixedWidth(100)
        else:
            edit = QLineEdit(path)
            edit.setPlaceholderText("Path to save file…" if mode == "file" else "Path to save folder…")
            browse_btn = QPushButton("Browse…")
            browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._make_browse(edit, mode))

        del_btn = QPushButton("×")
        del_btn.setObjectName("dangerBtn")
        del_btn.setFixedWidth(40)
        del_btn.clicked.connect(lambda: self._remove_game_row(entry))

        row_layout.addWidget(lbl)
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(browse_btn)
        row_layout.addWidget(del_btn)

        entry["edit"] = edit
        entry["widget"] = row

        self._game_entries.append(entry)
        self._paths_layout.addWidget(row)

    def _remove_game_row(self, entry: dict) -> None:
        entry["widget"].hide()
        entry["widget"].deleteLater()
        self._game_entries.remove(entry)

    def _on_add_game(self) -> None:
        dlg = AddGameDialog(self)
        if not dlg.exec():
            return
        name, mode, path = dlg.result
        if any(e["name"] == name for e in self._game_entries):
            QMessageBox.warning(self, "Duplicate", f"'{name}' is already in the list.")
            return
        # For "files" mode, path is already a "; "-separated string from AddGameDialog
        self._add_game_row(name, mode, path)

    def _make_browse(self, edit: QLineEdit, mode: str):
        def handler():
            if mode == "file":
                path, _ = QFileDialog.getOpenFileName(
                    self, "Select save file", edit.text() or ""
                )
                if path:
                    edit.setText(path)
            elif mode == "files":
                paths, _ = QFileDialog.getOpenFileNames(self, "Select save files", "")
                if paths:
                    existing = [p.strip() for p in edit.text().split(";") if p.strip()]
                    merged = existing + [p for p in paths if p not in existing]
                    edit.setText("; ".join(merged))
            else:
                path = QFileDialog.getExistingDirectory(
                    self, "Select save folder", edit.text() or ""
                )
                if path:
                    edit.setText(path)
        return handler

    def _on_save(self) -> None:
        self._cfg.confirm_replace = self._confirm_replace.isChecked()
        self._cfg.confirm_delete = self._confirm_delete.isChecked()
        self._cfg.auto_name_imports = self._auto_name.isChecked()
        self._cfg.show_save_path = self._show_save_path.isChecked()
        self._cfg.hotkey_import = self._hk_import.keySequence().toString()
        self._cfg.hotkey_load = self._hk_load.keySequence().toString()
        self._cfg.hotkey_ro_toggle = self._hk_ro.keySequence().toString()
        self.accept()

    @property
    def result_config(self) -> config.Config:
        return self._cfg

    @property
    def result_games(self) -> list[storage.GameConfig]:
        result = []
        for e in self._game_entries:
            if e["mode"] == "files":
                paths = [p.strip() for p in e["edit"].text().split(";") if p.strip()]
                result.append(storage.GameConfig(
                    name=e["name"], save_path="", save_mode="files", save_paths=paths,
                ))
            else:
                result.append(storage.GameConfig(
                    name=e["name"],
                    save_path=e["edit"].text().strip(),
                    save_mode=e["mode"],
                ))
        return result
