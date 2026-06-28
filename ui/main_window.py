import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QListWidget, QListWidgetItem, QLabel,
    QPushButton, QStatusBar, QSplitter, QFrame,
    QSizePolicy, QAbstractItemView, QPlainTextEdit, QInputDialog, QMessageBox, QMenu,
)

import config
import storage
from hotkeys import GlobalHotkeyListener
from ui.profiles_dialog import ProfilesDialog
from ui.settings_dialog import SettingsDialog


def _hotkey_label(key: str) -> str:
    if not key:
        return ""
    return QKeySequence(key).toString(QKeySequence.NativeText) or key


def _btn_text(base: str, key: str) -> str:
    label = _hotkey_label(key)
    return f"{base}  ({label})" if label else base


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FromSave Manager")

        self._config = config.load_config()
        self._games = storage.load_games()
        self._slots: list[storage.SaveSlot] = []
        self._current_slot: Optional[storage.SaveSlot] = None

        self._notes_save_timer = QTimer(self)
        self._notes_save_timer.setSingleShot(True)
        self._notes_save_timer.setInterval(600)
        self._notes_save_timer.timeout.connect(self._flush_notes)

        self._global_hotkeys = GlobalHotkeyListener(self)

        self._build_ui()
        self._apply_info_panel()

        # Restore saved window size (minimum is enforced by _sync_minimum_size via timer)
        w, h = self._config.window_width, self._config.window_height
        self.resize(w if w > 0 else 700, h if h > 0 else 580)

        self._global_hotkeys.import_triggered.connect(self._on_import_save)
        self._global_hotkeys.load_triggered.connect(self._on_load_save)
        self._global_hotkeys.ro_toggle_triggered.connect(self.ro_btn.toggle)

        self._load_data()
        self.apply_stylesheet()
        self._apply_path_visibility()
        self._apply_hotkeys()

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

        self._slot_panel = self._build_slot_panel()
        self._info_panel = self._build_info_panel()
        splitter.addWidget(self._slot_panel)
        splitter.addWidget(self._info_panel)

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

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Modified", "Created", "Name", "Custom"])
        self.sort_combo.setFixedWidth(115)
        _sort_label = {"modified": "Modified", "created": "Created", "name": "Name", "custom": "Custom"}
        self.sort_combo.setCurrentText(_sort_label.get(self._config.slot_sort, "Modified"))
        self.sort_combo.currentTextChanged.connect(self._on_sort_changed)
        header.addWidget(self.sort_combo)

        _ui_dir = Path(__file__).parent
        self._icon_sort_desc = QIcon(str(_ui_dir / "sort_desc.svg"))
        self._icon_sort_asc = QIcon(str(_ui_dir / "sort_asc.svg"))

        header.addSpacing(4)
        self.sort_dir_btn = QPushButton()
        self.sort_dir_btn.setIcon(self._icon_sort_desc if self._config.slot_sort_desc else self._icon_sort_asc)
        self.sort_dir_btn.setIconSize(QSize(16, 16))
        self.sort_dir_btn.setObjectName("ghostBtn")
        self.sort_dir_btn.setFixedWidth(36)
        self.sort_dir_btn.setEnabled(self._config.slot_sort != "custom")
        self.sort_dir_btn.setToolTip("Toggle ascending / descending")
        self.sort_dir_btn.clicked.connect(self._on_sort_dir_toggled)
        header.addWidget(self.sort_dir_btn)

        layout.addLayout(header)

        self.slot_list = QListWidget()
        self.slot_list.setAlternatingRowColors(False)
        self.slot_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.slot_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.slot_list.currentRowChanged.connect(self._on_slot_selected)
        self.slot_list.model().rowsMoved.connect(self._on_rows_moved)
        self.slot_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.slot_list.customContextMenuRequested.connect(self._on_slot_context_menu)
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
        self.info_file_size = _InfoRow("File size", "—")
        self.info_ro_status = _InfoRow("File status", "—")

        for row in (self.info_save_path, self.info_created, self.info_file_size, self.info_ro_status):
            info_layout.addWidget(row)

        layout.addWidget(info_box)
        layout.addStretch()

        return panel

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.import_btn = QPushButton(_btn_text("Import Save", self._config.hotkey_import))
        self.import_btn.setObjectName("primaryBtn")
        self.import_btn.clicked.connect(self._on_import_save)

        self.replace_btn = QPushButton("Replace Save")
        self.replace_btn.clicked.connect(self._on_replace_save)

        self.load_btn = QPushButton(_btn_text("Load Save", self._config.hotkey_load))
        self.load_btn.clicked.connect(self._on_load_save)

        self.delete_btn = QPushButton("Delete slot")
        self.delete_btn.setObjectName("dangerBtn")
        self.delete_btn.clicked.connect(self._on_delete_slot)

        bar.addWidget(self.import_btn)
        bar.addWidget(self.replace_btn)
        bar.addWidget(self.load_btn)
        bar.addWidget(self.delete_btn)
        bar.addStretch()

        self.ro_btn = QPushButton(_btn_text("  Toggle read-only", self._config.hotkey_ro_toggle))
        self.ro_btn.setObjectName("ghostBtn")
        self.ro_btn.setCheckable(True)
        self.ro_btn.setEnabled(False)
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

        if not self._games:
            self.profile_combo.clear()
            self._reload_slots()
            return

        # Restore last game, fall back to first
        game_idx = self.game_combo.findText(self._config.last_game)
        if game_idx < 0:
            game_idx = 0
        self.game_combo.setCurrentIndex(game_idx)

        # Load profiles for selected game
        game_name = self.game_combo.currentText()
        profiles = storage.load_profiles(game_name)
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for p in profiles:
            self.profile_combo.addItem(p)
        self.profile_combo.blockSignals(False)

        # Restore last profile, fall back to first
        if profiles:
            profile_idx = self.profile_combo.findText(self._config.last_profile)
            if profile_idx < 0:
                profile_idx = 0
            self.profile_combo.setCurrentIndex(profile_idx)

        # Update game info panel
        game_cfg = self._get_game_cfg()
        self.info_save_path.set_value(_game_path_display(game_cfg))

        # Load slots, restoring last selected slot
        self._reload_slots(self._config.last_slot)

    def _on_game_changed(self, _: int) -> None:
        game_name = self.game_combo.currentText()
        profiles = storage.load_profiles(game_name)

        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for p in profiles:
            self.profile_combo.addItem(p)
        self.profile_combo.blockSignals(False)

        game_cfg = next((g for g in self._games if g.name == game_name), None)
        self.info_save_path.set_value(_game_path_display(game_cfg))

        self._reload_slots()

    def _on_profile_changed(self, _: int) -> None:
        self._reload_slots()

    def _on_sort_changed(self, text: str) -> None:
        mode_map = {"Modified": "modified", "Created": "created", "Name": "name", "Custom": "custom"}
        mode = mode_map.get(text, "modified")
        if mode == self._config.slot_sort:
            return
        self._config.slot_sort = mode
        self.sort_dir_btn.setEnabled(mode != "custom")
        config.save_config(self._config)
        prev_slot = self._current_slot.name if self._current_slot else ""
        self._reload_slots(prev_slot)
        if mode == "custom":
            self.status_bar.showMessage("Custom order — drag slots to rearrange.", 4000)

    def _on_sort_dir_toggled(self) -> None:
        self._config.slot_sort_desc = not self._config.slot_sort_desc
        self.sort_dir_btn.setIcon(
            self._icon_sort_desc if self._config.slot_sort_desc else self._icon_sort_asc
        )
        config.save_config(self._config)
        prev_slot = self._current_slot.name if self._current_slot else ""
        self._reload_slots(prev_slot)

    def _on_rows_moved(self, *_) -> None:
        if self._config.slot_sort != "custom":
            return
        new_slots = []
        for i in range(self.slot_list.count()):
            new_slots.append(self.slot_list.item(i).data(Qt.UserRole))
        self._slots = new_slots
        storage.save_slot_order(
            self.game_combo.currentText(),
            self.profile_combo.currentText(),
            [s.name for s in self._slots],
        )
        QTimer.singleShot(0, self._reattach_slot_widgets)

    def _reattach_slot_widgets(self) -> None:
        compact = self._config.compact_list
        for i in range(self.slot_list.count()):
            item = self.slot_list.item(i)
            slot = item.data(Qt.UserRole)
            ts = _fmt_dt(slot.date_modified or slot.date_created)
            item.setSizeHint(QSize(0, 34 if compact else 52))
            self.slot_list.setItemWidget(item, _SlotItem(slot.name, ts, compact))

    def _reload_slots(self, select_slot: str = "") -> None:
        game_name = self.game_combo.currentText()
        profile_name = self.profile_combo.currentText()

        slots = (
            storage.load_slots(game_name, profile_name)
            if game_name and profile_name
            else []
        )

        sort_mode = self._config.slot_sort
        desc = self._config.slot_sort_desc
        if sort_mode == "name":
            slots.sort(key=lambda s: s.name.lower(), reverse=desc)
        elif sort_mode == "created":
            slots.sort(key=lambda s: s.date_created or datetime.min, reverse=desc)
        elif sort_mode == "modified":
            slots.sort(key=lambda s: s.date_modified or s.date_created or datetime.min, reverse=desc)
        elif sort_mode == "custom" and game_name and profile_name:
            order = storage.load_slot_order(game_name, profile_name)
            if order:
                order_map = {name: i for i, name in enumerate(order)}
                slots.sort(key=lambda s: order_map.get(s.name, len(order)))
            storage.save_slot_order(game_name, profile_name, [s.name for s in slots])

        is_custom = sort_mode == "custom"
        self.slot_list.setDragDropMode(
            QAbstractItemView.InternalMove if is_custom else QAbstractItemView.NoDragDrop
        )
        self.sort_dir_btn.setEnabled(not is_custom)

        compact = self._config.compact_list
        self._slots = slots
        self.slot_list.blockSignals(True)
        self.slot_list.clear()
        for slot in self._slots:
            ts = _fmt_dt(slot.date_modified or slot.date_created)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, slot)
            item.setSizeHint(QSize(0, 34 if compact else 52))
            self.slot_list.addItem(item)
            self.slot_list.setItemWidget(item, _SlotItem(slot.name, ts, compact))
        self.slot_list.blockSignals(False)

        if self._slots:
            target = 0
            if select_slot:
                for i, s in enumerate(self._slots):
                    if s.name == select_slot:
                        target = i
                        break
            self.slot_list.setCurrentRow(target)
            self._on_slot_selected(target)
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
        size = _slot_save_size(slot)
        self.info_file_size.set_value(_fmt_size(size) if size is not None else "—")
        save_files = _slot_save_files(slot)
        if save_files:
            is_ro = all(not os.access(f, os.W_OK) for f in save_files)
            self.info_ro_status.set_value("Read-only" if is_ro else "Writable")
            self.ro_btn.blockSignals(True)
            self.ro_btn.setChecked(is_ro)
            self.ro_btn.setText(self._ro_btn_text(is_ro))
            self.ro_btn.blockSignals(False)
            self.ro_btn.setEnabled(True)
        else:
            self.info_ro_status.set_value("—")
            self.ro_btn.blockSignals(True)
            self.ro_btn.setChecked(False)
            self.ro_btn.setText(self._ro_btn_text(False))
            self.ro_btn.blockSignals(False)
            self.ro_btn.setEnabled(False)

    def _clear_detail(self) -> None:
        self._current_slot = None
        self.rename_btn.setEnabled(False)
        self.detail_name.setText("—")
        self.detail_time.setText("—")
        self.detail_notes.blockSignals(True)
        self.detail_notes.setPlainText("")
        self.detail_notes.blockSignals(False)
        self.info_created.set_value("—")
        self.info_file_size.set_value("—")
        self.info_ro_status.set_value("—")
        self.ro_btn.blockSignals(True)
        self.ro_btn.setChecked(False)
        self.ro_btn.setText(self._ro_btn_text(False))
        self.ro_btn.blockSignals(False)
        self.ro_btn.setEnabled(False)

    def _on_notes_changed(self) -> None:
        self._notes_save_timer.start()

    def _flush_notes(self) -> None:
        self._notes_save_timer.stop()
        if self._current_slot is None:
            return
        storage.save_notes(self._current_slot, self.detail_notes.toPlainText())
        self.status_bar.showMessage("Notes saved.", 2000)

    def _on_ro_toggled(self, checked: bool) -> None:
        if not self._current_slot:
            return
        save_files = _slot_save_files(self._current_slot)
        if not save_files:
            return
        try:
            for f in save_files:
                mode = f.stat().st_mode
                os.chmod(f, (mode & ~0o222) if checked else (mode | 0o200))
            n = len(save_files)
            label = save_files[0].name if n == 1 else f"{n} files"
            self.ro_btn.setText(self._ro_btn_text(checked))
            self.info_ro_status.set_value("Read-only" if checked else "Writable")
            self.status_bar.showMessage(
                f"'{label}' {'locked read-only' if checked else 'is now writable'}."
            )
        except OSError as e:
            self.status_bar.showMessage(f"Failed to change permissions: {e}")
            self.ro_btn.blockSignals(True)
            self.ro_btn.setChecked(not checked)
            self.ro_btn.blockSignals(False)

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
        self._reload_slots(name)
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
        if any(not os.access(f, os.W_OK) for f in _slot_save_files(slot)):
            self.status_bar.showMessage(f"'{slot.name}' is read-only — unlock it before replacing.")
            return
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
        slot_name = slot.name
        try:
            storage.replace_save(slot, cfg)
        except Exception as e:
            self.status_bar.showMessage(f"Replace failed: {e}")
            return
        self._reload_slots(slot_name)
        self.status_bar.showMessage(f"Replaced '{slot_name}'.")

    def _on_load_save(self) -> None:
        row = self.slot_list.currentRow()
        if row < 0 or row >= len(self._slots):
            self.status_bar.showMessage("No slot selected.")
            return
        cfg = self._get_game_cfg()
        if not cfg or not self._validate_game_save_path(cfg):
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
        soft = self._config.soft_delete
        if self._config.confirm_delete:
            msg = (
                f"Move '{slot.name}' to trash?"
                if soft else
                f"Permanently delete '{slot.name}'?\n\nThis cannot be undone."
            )
            reply = QMessageBox.question(
                self, "Delete slot", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self._flush_notes()
        self._current_slot = None
        try:
            storage.delete_slot(slot, soft=soft)
        except Exception as e:
            self.status_bar.showMessage(f"Delete failed: {e}")
            return
        self._slots.pop(row)
        self.slot_list.blockSignals(True)
        self.slot_list.takeItem(row)
        self.slot_list.blockSignals(False)
        if self._slots:
            new_row = min(row, len(self._slots) - 1)
            self.slot_list.blockSignals(True)
            self.slot_list.setCurrentRow(new_row)
            self.slot_list.blockSignals(False)
            self._on_slot_selected(new_row)
        else:
            self._clear_detail()
        self.status_bar.showMessage(f"{'Moved to trash' if soft else 'Deleted'}: '{slot.name}'.")

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
        item = self.slot_list.item(row)
        ts = _fmt_dt(slot.date_modified or slot.date_created)
        self.slot_list.setItemWidget(item, _SlotItem(slot.name, ts, self._config.compact_list))
        self.detail_name.setText(slot.name)
        game_name = self.game_combo.currentText()
        profile_name = self.profile_combo.currentText()
        # Keep order.json in sync whenever it already exists, so the renamed slot
        # stays in position even if the user is not currently in Custom sort mode.
        if self._config.slot_sort == "custom" or storage.load_slot_order(game_name, profile_name):
            storage.save_slot_order(game_name, profile_name, [s.name for s in self._slots])
        self.status_bar.showMessage(f"Renamed to '{slot.name}'.")

    def _on_slot_context_menu(self, pos) -> None:
        item = self.slot_list.itemAt(pos)
        if not item:
            return
        row = self.slot_list.row(item)
        self.slot_list.setCurrentRow(row)

        menu = QMenu(self)
        menu.addAction("Rename", self._on_rename_slot)
        menu.addAction("Load save", self._on_load_save)
        menu.addSeparator()
        menu.addAction("Duplicate", self._on_duplicate_slot)
        menu.addAction("Copy to profile…", lambda: self._on_copy_to_profile(move=False))
        menu.addAction("Move to profile…", lambda: self._on_copy_to_profile(move=True))
        menu.addSeparator()
        menu.addAction("Delete", self._on_delete_slot)
        menu.exec(self.slot_list.mapToGlobal(pos))

    def _on_duplicate_slot(self) -> None:
        row = self.slot_list.currentRow()
        if row < 0 or row >= len(self._slots):
            return
        slot = self._slots[row]
        new_name = storage.duplicate_slot_name(
            self.game_combo.currentText(),
            self.profile_combo.currentText(),
            slot.name,
        )
        try:
            storage.duplicate_slot(slot, new_name)
        except Exception as e:
            self.status_bar.showMessage(f"Duplicate failed: {e}")
            return
        self._reload_slots(new_name)
        self.status_bar.showMessage(f"Duplicated as '{new_name}'.")

    def _on_copy_to_profile(self, move: bool = False) -> None:
        row = self.slot_list.currentRow()
        if row < 0 or row >= len(self._slots):
            return
        slot = self._slots[row]
        game = self.game_combo.currentText()
        current_profile = self.profile_combo.currentText()

        all_profiles = storage.load_profiles(game)
        other_profiles = [p for p in all_profiles if p != current_profile]
        if not other_profiles:
            self.status_bar.showMessage("No other profiles exist for this game.")
            return

        verb = "Move" if move else "Copy"
        if len(other_profiles) == 1:
            target_profile = other_profiles[0]
        else:
            target_profile, ok = QInputDialog.getItem(
                self, f"{verb} to profile", "Target profile:", other_profiles, 0, False
            )
            if not ok:
                return

        new_name = slot.name
        if (storage.SAVES_DIR / game / target_profile / new_name).exists():
            new_name = storage.duplicate_slot_name(game, target_profile, slot.name)

        try:
            storage.copy_slot_to_profile(slot, target_profile, new_name)
        except Exception as e:
            self.status_bar.showMessage(f"{verb} failed: {e}")
            return

        slot_name = slot.name
        if move:
            self._flush_notes()
            self._current_slot = None
            try:
                storage.delete_slot(slot, soft=self._config.soft_delete)
            except Exception as e:
                self.status_bar.showMessage(f"Copy succeeded but delete failed: {e}")
                return
            self._reload_slots()
            self.status_bar.showMessage(
                f"Moved '{slot_name}' to profile '{target_profile}'."
            )
        else:
            self.status_bar.showMessage(
                f"Copied '{slot_name}' to profile '{target_profile}'"
                + (f" as '{new_name}'." if new_name != slot_name else ".")
            )

    def _on_open_settings(self) -> None:
        prev_game = self.game_combo.currentText()
        prev_profile = self.profile_combo.currentText()
        prev_slot = self._current_slot.name if self._current_slot else ""

        dlg = SettingsDialog(self._config, self._games, self)
        if not dlg.exec():
            return

        self._config = dlg.result_config
        config.save_config(self._config)
        self._games = dlg.result_games
        storage.save_games(self._games)

        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        for game in self._games:
            self.game_combo.addItem(game.name)
        self.game_combo.blockSignals(False)

        if self._games:
            game_idx = max(0, self.game_combo.findText(prev_game))
            self.game_combo.setCurrentIndex(game_idx)

            game_name = self.game_combo.currentText()
            profiles = storage.load_profiles(game_name)
            self.profile_combo.blockSignals(True)
            self.profile_combo.clear()
            for p in profiles:
                self.profile_combo.addItem(p)
            self.profile_combo.blockSignals(False)

            if profiles:
                profile_idx = max(0, self.profile_combo.findText(prev_profile))
                self.profile_combo.setCurrentIndex(profile_idx)

            game_cfg = self._get_game_cfg()
            self.info_save_path.set_value(_game_path_display(game_cfg))

            self._reload_slots(prev_slot)
        else:
            self.profile_combo.blockSignals(True)
            self.profile_combo.clear()
            self.profile_combo.blockSignals(False)
            self._reload_slots()

        self._apply_path_visibility()
        self._apply_info_panel()
        self._apply_hotkeys()
        self.status_bar.showMessage("Settings saved.")

    def _ro_btn_text(self, is_on: bool) -> str:
        key = _hotkey_label(self._config.hotkey_ro_toggle)
        if is_on:
            return _btn_text("Read-only ON", key)
        return _btn_text("  Toggle read-only", key)

    def _apply_hotkeys(self) -> None:
        for sc in getattr(self, "_shortcuts", []):
            sc.setEnabled(False)
            sc.deleteLater()
        self._shortcuts: list[QShortcut] = []

        def _bind(key: str, slot) -> None:
            if key:
                sc = QShortcut(QKeySequence(key), self)
                sc.activated.connect(slot)
                self._shortcuts.append(sc)

        cfg = self._config
        _bind(cfg.hotkey_import, self._on_import_save)
        _bind(cfg.hotkey_load, self._on_load_save)
        _bind(cfg.hotkey_ro_toggle, self.ro_btn.toggle)

        self.import_btn.setText(_btn_text("Import Save", cfg.hotkey_import))
        self.load_btn.setText(_btn_text("Load Save", cfg.hotkey_load))
        self.ro_btn.setText(self._ro_btn_text(self.ro_btn.isChecked()))

        started = self._global_hotkeys.start(cfg.hotkey_import, cfg.hotkey_load, cfg.hotkey_ro_toggle)
        if not started and any([cfg.hotkey_import, cfg.hotkey_load, cfg.hotkey_ro_toggle]):
            self.status_bar.showMessage(
                "Global hotkeys unavailable — grant Accessibility permission in System Settings and restart.", 6000
            )

    def _apply_info_panel(self) -> None:
        hide = self._config.hide_details
        self._info_panel.setVisible(not hide)
        self._slot_panel.setMaximumWidth(16777215 if hide else 380)
        QTimer.singleShot(0, self._sync_minimum_size)

    def _sync_minimum_size(self) -> None:
        hint = self.minimumSizeHint()
        self.setMinimumSize(hint)
        w = max(self.width(), hint.width())
        h = max(self.height(), hint.height())
        if w != self.width() or h != self.height():
            self.resize(w, h)

    def _apply_path_visibility(self) -> None:
        self.info_save_path.setVisible(self._config.show_save_path)

    def _get_game_cfg(self) -> Optional[storage.GameConfig]:
        game_name = self.game_combo.currentText()
        return next((g for g in self._games if g.name == game_name), None)

    def _validate_game_save_path(self, cfg: storage.GameConfig) -> bool:
        if cfg.save_mode == "files":
            if not cfg.save_paths:
                self.status_bar.showMessage("No save files configured for this game.")
                return False
            missing = [p for p in cfg.save_paths if not Path(p).exists()]
            if missing:
                self.status_bar.showMessage(f"Save file not found: {missing[0]}")
                return False
            return True
        if not cfg.save_path:
            self.status_bar.showMessage("Save path is not configured for this game.")
            return False
        src = Path(cfg.save_path)
        if not src.exists():
            self.status_bar.showMessage(f"Save path not found: {src}")
            return False
        return True

    def closeEvent(self, event) -> None:
        self._global_hotkeys.stop()
        self._flush_notes()
        self._config.last_game = self.game_combo.currentText()
        self._config.last_profile = self.profile_combo.currentText()
        self._config.last_slot = self._current_slot.name if self._current_slot else ""
        self._config.window_width = self.width()
        self._config.window_height = self.height()
        config.save_config(self._config)
        super().closeEvent(event)

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


def _game_path_display(cfg: Optional[storage.GameConfig]) -> str:
    if not cfg:
        return "—"
    if cfg.save_mode == "files":
        n = len(cfg.save_paths)
        return f"{n} file{'s' if n != 1 else ''}" if n else "—"
    return cfg.save_path or "—"


def _slot_save_files(slot: storage.SaveSlot) -> list[Path]:
    """Return all save files for a slot, regardless of save mode."""
    save_data = slot.path / "save_data"
    if save_data.exists():
        return [f for f in save_data.rglob("*") if f.is_file()]
    return [
        f for f in slot.path.iterdir()
        if f.is_file() and f.name not in storage._RESERVED and not f.name.startswith(".")
    ]


def _slot_save_size(slot: storage.SaveSlot) -> Optional[int]:
    save_data = slot.path / "save_data"
    if save_data.exists():
        return sum(f.stat().st_size for f in save_data.rglob("*") if f.is_file())
    files = [
        f for f in slot.path.iterdir()
        if f.is_file() and f.name not in storage._RESERVED and not f.name.startswith(".")
    ]
    return sum(f.stat().st_size for f in files) if files else None


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d  %H:%M:%S")


class _SlotItem(QWidget):
    """Custom widget for each row in the slot list."""

    def __init__(self, name: str, timestamp: str, compact: bool = False) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6 if compact else 8, 12, 6 if compact else 8)
        layout.setSpacing(2)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("font-size: 13px; font-weight: 500; color: #d4cfc8;")
        layout.addWidget(name_lbl)

        if not compact:
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
