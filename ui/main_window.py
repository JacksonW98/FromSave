import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QListWidget, QListWidgetItem, QLabel,
    QPushButton, QStatusBar, QSplitter, QFrame,
    QSizePolicy, QAbstractItemView,
)

import storage


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FromSave Manager")
        self.resize(920, 580)
        self.setMinimumSize(700, 440)

        self._games = storage.load_games()
        self._slots: list[storage.SaveSlot] = []

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

        bar.addStretch()

        self.hotkey_indicator = QLabel("F5  backup   F9  restore   F6  read-only")
        self.hotkey_indicator.setObjectName("hotkeyHint")
        bar.addWidget(self.hotkey_indicator)

        bar.addSpacing(16)

        self.settings_btn = QPushButton("⚙  Settings")
        self.settings_btn.setObjectName("ghostBtn")
        self.settings_btn.clicked.connect(self._stub("Open settings"))
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

        self.detail_name = QLabel("—")
        self.detail_name.setObjectName("detailName")
        layout.addWidget(self.detail_name)

        self.detail_time = QLabel("—")
        self.detail_time.setObjectName("mutedLabel")
        layout.addWidget(self.detail_time)

        layout.addSpacing(16)

        notes_lbl = QLabel("Notes")
        notes_lbl.setObjectName("fieldLabel")
        layout.addWidget(notes_lbl)
        layout.addSpacing(4)

        self.detail_notes = QLabel("—")
        self.detail_notes.setObjectName("detailNotes")
        self.detail_notes.setWordWrap(True)
        self.detail_notes.setAlignment(Qt.AlignTop)
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

        self.backup_btn = QPushButton("Backup  (F5)")
        self.backup_btn.setObjectName("primaryBtn")
        self.backup_btn.clicked.connect(self._stub("Backup save"))

        self.restore_btn = QPushButton("Restore  (F9)")
        self.restore_btn.clicked.connect(self._stub("Restore save"))

        self.delete_btn = QPushButton("Delete slot")
        self.delete_btn.setObjectName("dangerBtn")
        self.delete_btn.clicked.connect(self._stub("Delete slot"))

        bar.addWidget(self.backup_btn)
        bar.addWidget(self.restore_btn)
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
        if row < 0 or row >= len(self._slots):
            self._clear_detail()
            return
        slot = self._slots[row]
        self.detail_name.setText(slot.name)
        self.detail_time.setText(_fmt_dt(slot.date_modified or slot.date_created))
        self.detail_notes.setText(slot.notes or "—")
        self.info_created.set_value(_fmt_dt(slot.date_created))

        if slot.save_file:
            save_path = slot.path / slot.save_file
            self.info_ro_status.set_value("Read-only" if not os.access(save_path, os.W_OK) else "Writable")
        else:
            self.info_ro_status.set_value("—")

    def _clear_detail(self) -> None:
        self.detail_name.setText("—")
        self.detail_time.setText("—")
        self.detail_notes.setText("—")
        self.info_created.set_value("—")
        self.info_ro_status.set_value("—")

    def _on_ro_toggled(self, checked: bool) -> None:
        if checked:
            self.ro_btn.setText("Read-only ON  (F6)")
            self.info_ro_status.set_value("Read-only")
            self.status_bar.showMessage("Save file is now read-only.")
        else:
            self.ro_btn.setText("  Toggle read-only  (F6)")
            self.info_ro_status.set_value("✔   Writable")
            self.status_bar.showMessage("Save file is now writable.")

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
