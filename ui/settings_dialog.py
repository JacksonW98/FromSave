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
            slot_sort=cfg.slot_sort,
            slot_sort_desc=cfg.slot_sort_desc,
            last_game=cfg.last_game,
            last_profile=cfg.last_profile,
            last_slot=cfg.last_slot,
            hotkey_import=cfg.hotkey_import,
            hotkey_load=cfg.hotkey_load,
            hotkey_replace=cfg.hotkey_replace,
            hotkey_ro_toggle=cfg.hotkey_ro_toggle,
            hotkey_next_slot=cfg.hotkey_next_slot,
            hotkey_prev_slot=cfg.hotkey_prev_slot,
            global_hotkeys_enabled=cfg.global_hotkeys_enabled,
            soft_delete=cfg.soft_delete,
            compact_list=cfg.compact_list,
            hide_details=cfg.hide_details,
            window_width=cfg.window_width,
            window_height=cfg.window_height,
        )
        self._initial_cfg = (
            cfg.confirm_delete, cfg.confirm_replace, cfg.auto_name_imports,
            cfg.show_save_path, cfg.soft_delete, cfg.compact_list, cfg.hide_details,
            cfg.hotkey_import, cfg.hotkey_load, cfg.hotkey_replace, cfg.hotkey_ro_toggle,
            cfg.hotkey_next_slot, cfg.hotkey_prev_slot, cfg.global_hotkeys_enabled,
        )
        self._initial_games = [
            (g.name, g.save_mode,
             g.save_path if g.save_mode != "files" else "",
             tuple(g.save_paths) if g.save_mode == "files" else ())
            for g in games
        ]
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
        self._soft_delete = QCheckBox("Send deleted saves to the system trash instead of permanently deleting")
        self._soft_delete.setChecked(self._cfg.soft_delete)
        self._compact_list = QCheckBox("Compact saves list  (hide dates, show more saves)")
        self._compact_list.setChecked(self._cfg.compact_list)
        self._hide_details = QCheckBox("Hide details panel  (slot name, notes, and game info)")
        self._hide_details.setChecked(self._cfg.hide_details)
        behaviour_layout.addWidget(self._confirm_replace)
        behaviour_layout.addWidget(self._confirm_delete)
        behaviour_layout.addWidget(self._show_save_path)
        behaviour_layout.addWidget(self._soft_delete)
        behaviour_layout.addWidget(self._compact_list)
        behaviour_layout.addWidget(self._hide_details)

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

        self._global_hotkeys_enabled = QCheckBox("Enable global hotkeys (work while the app is in the background)")
        self._global_hotkeys_enabled.setChecked(self._cfg.global_hotkeys_enabled)
        hotkeys_layout.addWidget(self._global_hotkeys_enabled)

        self._hk_import = self._make_hotkey_row(hotkeys_layout, "Import save", self._cfg.hotkey_import)
        self._hk_load = self._make_hotkey_row(hotkeys_layout, "Load save", self._cfg.hotkey_load)
        self._hk_replace = self._make_hotkey_row(hotkeys_layout, "Replace save", self._cfg.hotkey_replace)
        self._hk_ro = self._make_hotkey_row(hotkeys_layout, "Protect save", self._cfg.hotkey_ro_toggle)
        self._hk_next_slot = self._make_hotkey_row(hotkeys_layout, "Next slot", self._cfg.hotkey_next_slot)
        self._hk_prev_slot = self._make_hotkey_row(hotkeys_layout, "Previous slot", self._cfg.hotkey_prev_slot)
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
        reply = QMessageBox.question(
            self, "Remove game",
            f"Remove '{entry['name']}' from the list?\n\nThis will not delete any saved slots.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
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

    def _has_changes(self) -> bool:
        current_cfg = (
            self._confirm_delete.isChecked(),
            self._confirm_replace.isChecked(),
            self._auto_name.isChecked(),
            self._show_save_path.isChecked(),
            self._soft_delete.isChecked(),
            self._compact_list.isChecked(),
            self._hide_details.isChecked(),
            self._hk_import.keySequence().toString(),
            self._hk_load.keySequence().toString(),
            self._hk_replace.keySequence().toString(),
            self._hk_ro.keySequence().toString(),
            self._hk_next_slot.keySequence().toString(),
            self._hk_prev_slot.keySequence().toString(),
            self._global_hotkeys_enabled.isChecked(),
        )
        if current_cfg != self._initial_cfg:
            return True
        current_games = []
        for e in self._game_entries:
            if e["mode"] == "files":
                paths = tuple(p.strip() for p in e["edit"].text().split(";") if p.strip())
                current_games.append((e["name"], e["mode"], "", paths))
            else:
                current_games.append((e["name"], e["mode"], e["edit"].text().strip(), ()))
        return current_games != self._initial_games

    def reject(self) -> None:
        if self._has_changes():
            reply = QMessageBox.question(
                self, "Discard changes",
                "You have unsaved changes. Close without saving?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        super().reject()

    def _on_save(self) -> None:
        self._cfg.confirm_replace = self._confirm_replace.isChecked()
        self._cfg.confirm_delete = self._confirm_delete.isChecked()
        self._cfg.auto_name_imports = self._auto_name.isChecked()
        self._cfg.show_save_path = self._show_save_path.isChecked()
        self._cfg.hotkey_import = self._hk_import.keySequence().toString()
        self._cfg.hotkey_load = self._hk_load.keySequence().toString()
        self._cfg.hotkey_replace = self._hk_replace.keySequence().toString()
        self._cfg.hotkey_ro_toggle = self._hk_ro.keySequence().toString()
        self._cfg.hotkey_next_slot = self._hk_next_slot.keySequence().toString()
        self._cfg.hotkey_prev_slot = self._hk_prev_slot.keySequence().toString()
        self._cfg.global_hotkeys_enabled = self._global_hotkeys_enabled.isChecked()
        self._cfg.soft_delete = self._soft_delete.isChecked()
        self._cfg.compact_list = self._compact_list.isChecked()
        self._cfg.hide_details = self._hide_details.isChecked()
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
