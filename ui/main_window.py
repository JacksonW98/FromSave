import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QListWidget, QListWidgetItem, QLabel,
    QPushButton, QStatusBar, QSplitter, QFrame,
    QSizePolicy, QAbstractItemView, QPlainTextEdit, QInputDialog, QMessageBox,
)

import config
import storage
from ui.profiles_dialog import ProfilesDialog
from ui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FromSave Manager")
        self.resize(920, 580)
        self.setMinimumSize(700, 440)

        self._config = config.load_config()
        self._games = storage.load_games()
        self._slots: list[storage.SaveSlot] = []
        self._current_slot: Optional[storage.SaveSlot] = None

        self._notes_save_timer = QTimer(self)
        self._notes_save_timer.setSingleShot(True)
        self._notes_save_timer.setInterval(600)
        self._notes_save_timer.timeout.connect(self._flush_notes)

        self._build_ui()
        self._load_data()
        self.apply_stylesheet()

    # UI construction

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 12, 14, 10)
        content_layout.setSpacing(10)
        outer.addWidget(content, 1)

        content_layout.addLayout(self._build_top_bar())
        content_layout.addWidget(_Divider())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        splitter.addWidget(self._build_slot_panel())
        splitter.addWidget(self._build_info_panel())

        splitter.setSizes([310, 580])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        content_layout.addWidget(splitter, 1)

        content_layout.addWidget(_Divider())
        content_layout.addLayout(self._build_action_bar())

        self.status_bar = QStatusBar()
        self.status_bar.setSizeGripEnabled(True)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready.")

    def _build_top_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(10)

        game_label = QLabel("Game")
        game_label.setObjectName("fieldLabel")
        bar.addWidget(game_label)

        self.game_combo = QComboBox()
        self.game_combo.setMinimumWidth(220)
        self.game_combo.setMaximumWidth(320)
        self.game_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.game_combo.currentIndexChanged.connect(self._on_game_changed)
        bar.addWidget(self.game_combo)

        bar.addSpacing(12)

        profile_label = QLabel("Profile")
        profile_label.setObjectName("fieldLabel")
        bar.addWidget(profile_label)

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(140)
        self.profile_combo.setMaximumWidth(220)
        self.profile_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        bar.addWidget(self.profile_combo)

        self.manage_profiles_btn = QPushButton("···")
        self.manage_profiles_btn.setObjectName("ghostBtn")
        self.manage_profiles_btn.setFixedWidth(48)
        self.manage_profiles_btn.setToolTip("Manage profiles")
        self.manage_profiles_btn.clicked.connect(self._on_manage_profiles)
        bar.addWidget(self.manage_profiles_btn)

        bar.addStretch()

        self.hotkey_indicator = QLabel("F5  import   F9  load   F6  read-only")
        self.hotkey_indicator.setObjectName("hotkeyHint")
        bar.addWidget(self.hotkey_indicator)

        bar.addSpacing(16)

        self.settings_btn = QPushButton("⚙  Settings")
        self.settings_btn.setObjectName("ghostBtn")
        self.settings_btn.clicked.connect(self._on_open_settings)
        bar.addWidget(self.settings_btn)

        return bar

    def _build_slot_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(240)
        panel.setMaximumWidth(380)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        lbl = QLabel("Save slots")
        lbl.setObjectName("panelHeader")
        header.addWidget(lbl)
        header.addStretch()

        self.slot_count_label = QLabel("0 slots")
        self.slot_count_label.setObjectName("mutedLabel")
        header.addWidget(self.slot_count_label)
        layout.addLayout(header)

        self.slot_list = QListWidget()
        self.slot_list.setAlternatingRowColors(False)
        self.slot_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.slot_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.slot_list.currentRowChanged.connect(self._on_slot_selected)
        layout.addWidget(self.slot_list, 1)

        return panel

    def _build_info_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)

        lbl = QLabel("Slot details")
        lbl.setObjectName("panelHeader")
        layout.addWidget(lbl)
        layout.addSpacing(10)

        name_row = QHBoxLayout()
        self.detail_name = QLabel("—")
        self.detail_name.setObjectName("detailName")
        name_row.addWidget(self.detail_name, 1)
        self.rename_btn = QPushButton("Rename")
        self.rename_btn.setObjectName("ghostBtn")
        self.rename_btn.setEnabled(False)
        self.rename_btn.clicked.connect(self._on_rename_slot)
        name_row.addWidget(self.rename_btn)
        layout.addLayout(name_row)

        self.detail_time = QLabel("—")
        self.detail_time.setObjectName("mutedLabel")
        layout.addWidget(self.detail_time)

        layout.addSpacing(16)

        notes_lbl = QLabel("Notes")
        notes_lbl.setObjectName("fieldLabel")
        layout.addWidget(notes_lbl)
        layout.addSpacing(4)

        self.detail_notes = QPlainTextEdit()
        self.detail_notes.setObjectName("detailNotes")
        self.detail_notes.setPlaceholderText("No notes.")
        self.detail_notes.setMaximumHeight(110)
        self.detail_notes.textChanged.connect(self._on_notes_changed)
        layout.addWidget(self.detail_notes)

        layout.addSpacing(24)

        info_box = QFrame()
        info_box.setObjectName("infoBox")
        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(6)

        info_title = QLabel("Game info")
        info_title.setObjectName("fieldLabel")
        info_layout.addWidget(info_title)

        self.info_save_path = _InfoRow("Save path", "—")
        self.info_created = _InfoRow("Created", "—")
        self.info_ro_status = _InfoRow("File status", "—")

        for row in (self.info_save_path, self.info_created, self.info_ro_status):
            info_layout.addWidget(row)

        layout.addWidget(info_box)
        layout.addStretch()

        return panel

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.import_btn = QPushButton("Import Save  (F5)")
        self.import_btn.setObjectName("primaryBtn")
        self.import_btn.clicked.connect(self._on_import_save)

        self.replace_btn = QPushButton("Replace Save")
        self.replace_btn.clicked.connect(self._on_replace_save)

        self.load_btn = QPushButton("Load Save  (F9)")
        self.load_btn.clicked.connect(self._on_load_save)

        self.delete_btn = QPushButton("Delete slot")
        self.delete_btn.setObjectName("dangerBtn")
        self.delete_btn.clicked.connect(self._on_delete_slot)

        bar.addWidget(self.import_btn)
        bar.addWidget(self.replace_btn)
        bar.addWidget(self.load_btn)
        bar.addWidget(self.delete_btn)
        bar.addStretch()

        self.ro_btn = QPushButton("  Toggle read-only  (F6)")
        self.ro_btn.setObjectName("ghostBtn")
        self.ro_btn.setCheckable(True)
        self.ro_btn.toggled.connect(self._on_ro_toggled)
        bar.addWidget(self.ro_btn)

        return bar

    # Data loading

    def _load_data(self) -> None:
        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        for game in self._games:
            self.game_combo.addItem(game.name)
        self.game_combo.blockSignals(False)

        if self._games:
            self._on_game_changed(0)
        else:
            self.profile_combo.clear()
            self._reload_slots()

    def _on_game_changed(self, _: int) -> None:
        game_name = self.game_combo.currentText()
        profiles = storage.load_profiles(game_name)

        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for p in profiles:
            self.profile_combo.addItem(p)
        self.profile_combo.blockSignals(False)

        game_cfg = next((g for g in self._games if g.name == game_name), None)
        self.info_save_path.set_value(game_cfg.save_path if (game_cfg and game_cfg.save_path) else "—")

        self._reload_slots()

    def _on_profile_changed(self, _: int) -> None:
        self._reload_slots()

    def _reload_slots(self) -> None:
        game_name = self.game_combo.currentText()
        profile_name = self.profile_combo.currentText()

        self._slots = (
            storage.load_slots(game_name, profile_name)
            if game_name and profile_name
            else []
        )

        self.slot_list.blockSignals(True)
        self.slot_list.clear()
        for slot in self._slots:
            ts = _fmt_dt(slot.date_modified or slot.date_created)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, slot)
            item.setSizeHint(QSize(0, 52))
            self.slot_list.addItem(item)
            self.slot_list.setItemWidget(item, _SlotItem(slot.name, ts))
        self.slot_list.blockSignals(False)

        count = len(self._slots)
        self.slot_count_label.setText(f"{count} slot{'s' if count != 1 else ''}")

        if self._slots:
            self.slot_list.setCurrentRow(0)
            self._on_slot_selected(0)
        else:
            self._clear_detail()

    # Event handlers

    def _on_slot_selected(self, row: int) -> None:
        self._flush_notes()
        if row < 0 or row >= len(self._slots):
            self._clear_detail()
            return
        slot = self._slots[row]
        self._current_slot = slot
        self.rename_btn.setEnabled(True)
        self.detail_name.setText(slot.name)
        self.detail_time.setText(_fmt_dt(slot.date_modified or slot.date_created))
        self.detail_notes.blockSignals(True)
        self.detail_notes.setPlainText(slot.notes)
        self.detail_notes.blockSignals(False)
        self.info_created.set_value(_fmt_dt(slot.date_created))
        save_path = slot.path / slot.save_file
        self.info_ro_status.set_value("Read-only" if not os.access(save_path, os.W_OK) else "Writable")

    def _clear_detail(self) -> None:
        self._current_slot = None
        self.rename_btn.setEnabled(False)
        self.detail_name.setText("—")
        self.detail_time.setText("—")
        self.detail_notes.blockSignals(True)
        self.detail_notes.setPlainText("")
        self.detail_notes.blockSignals(False)
        self.info_created.set_value("—")
        self.info_ro_status.set_value("—")

    def _on_notes_changed(self) -> None:
        self._notes_save_timer.start()

    def _flush_notes(self) -> None:
        self._notes_save_timer.stop()
        if self._current_slot is None:
            return
        storage.save_notes(self._current_slot, self.detail_notes.toPlainText())
        self.status_bar.showMessage("Notes saved.", 2000)

    def _on_ro_toggled(self, checked: bool) -> None:
        if checked:
            self.ro_btn.setText("Read-only ON  (F6)")
            self.info_ro_status.set_value("Read-only")
            self.status_bar.showMessage("Save file is now read-only.")
        else:
            self.ro_btn.setText("  Toggle read-only  (F6)")
            self.info_ro_status.set_value("Writable")
            self.status_bar.showMessage("Save file is now writable.")

    def _on_import_save(self) -> None:
        cfg = self._get_game_cfg()
        if not cfg or not self._validate_game_save_path(cfg):
            return
        profile = self.profile_combo.currentText()
        if not profile:
            self.status_bar.showMessage("No profile selected.")
            return
        if self._config.auto_name_imports:
            name = storage.auto_slot_name(self.game_combo.currentText(), profile)
        else:
            name, ok = QInputDialog.getText(self, "Import Save", "Slot name:")
            if not ok or not name.strip():
                return
            name = name.strip()
        slot_dir = storage.SAVES_DIR / self.game_combo.currentText() / profile / name
        if slot_dir.exists():
            self.status_bar.showMessage(f"A slot named '{name}' already exists.")
            return
        try:
            storage.import_save(self.game_combo.currentText(), profile, name, cfg)
        except Exception as e:
            self.status_bar.showMessage(f"Import failed: {e}")
            return
        self._reload_slots()
        for i, s in enumerate(self._slots):
            if s.name == name:
                self.slot_list.setCurrentRow(i)
                break
        self.status_bar.showMessage(f"Imported '{name}'.")

    def _on_replace_save(self) -> None:
        row = self.slot_list.currentRow()
        if row < 0 or row >= len(self._slots):
            self.status_bar.showMessage("No slot selected.")
            return
        cfg = self._get_game_cfg()
        if not cfg or not self._validate_game_save_path(cfg):
            return
        slot = self._slots[row]
        if self._config.confirm_replace:
            reply = QMessageBox.question(
                self,
                "Replace save",
                f"Overwrite '{slot.name}' with the current game save?\n\nThis cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        try:
            storage.replace_save(slot, cfg)
        except Exception as e:
            self.status_bar.showMessage(f"Replace failed: {e}")
            return
        ts = _fmt_dt(slot.date_modified or slot.date_created)
        self.slot_list.setItemWidget(self.slot_list.item(row), _SlotItem(slot.name, ts))
        self._on_slot_selected(row)
        self.status_bar.showMessage(f"Replaced '{slot.name}'.")

    def _on_load_save(self) -> None:
        row = self.slot_list.currentRow()
        if row < 0 or row >= len(self._slots):
            self.status_bar.showMessage("No slot selected.")
            return
        cfg = self._get_game_cfg()
        if not cfg:
            return
        if not cfg.save_path:
            self.status_bar.showMessage("Save path is not configured for this game.")
            return
        slot = self._slots[row]
        try:
            storage.load_save(slot, cfg)
        except Exception as e:
            self.status_bar.showMessage(f"Load failed: {e}")
            return
        self.status_bar.showMessage(f"Loaded '{slot.name}' to game save.")

    def _on_delete_slot(self) -> None:
        row = self.slot_list.currentRow()
        if row < 0 or row >= len(self._slots):
            self.status_bar.showMessage("No slot selected.")
            return
        slot = self._slots[row]
        if self._config.confirm_delete:
            reply = QMessageBox.question(
                self,
                "Delete slot",
                f"Permanently delete '{slot.name}'?\n\nThis cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self._flush_notes()
        self._current_slot = None
        try:
            storage.delete_slot(slot)
        except Exception as e:
            self.status_bar.showMessage(f"Delete failed: {e}")
            return
        self._slots.pop(row)
        self.slot_list.blockSignals(True)
        self.slot_list.takeItem(row)
        self.slot_list.blockSignals(False)
        count = len(self._slots)
        self.slot_count_label.setText(f"{count} slot{'s' if count != 1 else ''}")
        if self._slots:
            new_row = min(row, count - 1)
            self.slot_list.blockSignals(True)
            self.slot_list.setCurrentRow(new_row)
            self.slot_list.blockSignals(False)
            self._on_slot_selected(new_row)
        else:
            self._clear_detail()
        self.status_bar.showMessage(f"Deleted '{slot.name}'.")

    def _on_manage_profiles(self) -> None:
        game = self.game_combo.currentText()
        if not game:
            return
        previous = self.profile_combo.currentText()
        ProfilesDialog(game, self).exec()
        self._flush_notes()
        self._current_slot = None
        profiles = storage.load_profiles(game)
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for p in profiles:
            self.profile_combo.addItem(p)
        self.profile_combo.blockSignals(False)
        idx = self.profile_combo.findText(previous)
        self.profile_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._reload_slots()

    def _on_rename_slot(self) -> None:
        row = self.slot_list.currentRow()
        if row < 0 or row >= len(self._slots):
            return
        slot = self._slots[row]
        name, ok = QInputDialog.getText(self, "Rename slot", "New name:", text=slot.name)
        if not ok or not name.strip() or name.strip() == slot.name:
            return
        name = name.strip()
        if (slot.path.parent / name).exists():
            self.status_bar.showMessage(f"A slot named '{name}' already exists.")
            return
        try:
            storage.rename_slot(slot, name)
        except Exception as e:
            self.status_bar.showMessage(f"Rename failed: {e}")
            return
        ts = _fmt_dt(slot.date_modified or slot.date_created)
        self.slot_list.setItemWidget(self.slot_list.item(row), _SlotItem(slot.name, ts))
        self.detail_name.setText(slot.name)
        self.status_bar.showMessage(f"Renamed to '{slot.name}'.")

    def _on_open_settings(self) -> None:
        dlg = SettingsDialog(self._config, self._games, self)
        if not dlg.exec():
            return
        self._config = dlg.result_config
        config.save_config(self._config)
        new_paths = dlg.result_paths
        for game in self._games:
            if game.name in new_paths:
                game.save_path = new_paths[game.name]
        storage.save_games(self._games)
        game_cfg = self._get_game_cfg()
        self.info_save_path.set_value(
            game_cfg.save_path if (game_cfg and game_cfg.save_path) else "—"
        )
        self.status_bar.showMessage("Settings saved.")

    def _get_game_cfg(self) -> Optional[storage.GameConfig]:
        game_name = self.game_combo.currentText()
        return next((g for g in self._games if g.name == game_name), None)

    def _validate_game_save_path(self, cfg: storage.GameConfig) -> bool:
        if not cfg.save_path:
            self.status_bar.showMessage("Save path is not configured for this game.")
            return False
        src = Path(cfg.save_path)
        if not src.exists():
            self.status_bar.showMessage(f"Save file not found: {src}")
            return False
        return True

    def _stub(self, action: str):
        def handler():
            self.status_bar.showMessage(f"[stub] {action} — not yet implemented.")
        return handler

    def apply_stylesheet(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        stylesheet_path = os.path.join(script_dir, 'main_window.qtt')
        try:
            with open(stylesheet_path, 'r') as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            print(f"Style sheet file not found at: {stylesheet_path}")


def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d  %H:%M:%S")


class _SlotItem(QWidget):
    """Custom widget for each row in the slot list."""

    def __init__(self, name: str, timestamp: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("font-size: 13px; font-weight: 500; color: #d4cfc8;")
        layout.addWidget(name_lbl)

        ts_lbl = QLabel(timestamp)
        ts_lbl.setStyleSheet("font-size: 11px; color: #555566;")
        layout.addWidget(ts_lbl)

    def setSelected(self, selected: bool) -> None:
        bg = "#1e1e26" if selected else "transparent"
        self.setStyleSheet(f"background: {bg};")


class _InfoRow(QWidget):
    """Label + value pair inside the info box."""

    def __init__(self, label: str, value: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._lbl = QLabel(label)
        self._lbl.setObjectName("fieldLabel")
        self._lbl.setFixedWidth(72)
        layout.addWidget(self._lbl)

        self._val = QLabel(value)
        self._val.setStyleSheet("color: #9999aa; font-size: 12px;")
        self._val.setWordWrap(True)
        layout.addWidget(self._val, 1)

    def set_value(self, value: str) -> None:
        self._val.setText(value)


class _Divider(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet("background: #2a2a32; border: none;")


class _Banner(QFrame):
    """Coloured info/warning banner that sits at the top."""

    def __init__(self, text: str, bg: str, fg: str) -> None:
        super().__init__()
        self.setStyleSheet(f"background: {bg}; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)

        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {fg}; font-size: 12px; background: transparent;")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
