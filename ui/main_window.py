import os

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor, QPalette, QFontDatabase
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QListWidget, QListWidgetItem, QLabel,
    QPushButton, QStatusBar, QSplitter, QFrame,
    QToolButton, QSizePolicy, QMessageBox, QAbstractItemView,
    QGroupBox, QScrollArea,
)


# Placeholders TODO add real data loading and saving
PLACEHOLDER_GAMES = [
    "Elden Ring",
    "Elden Ring Nightreign",
    "Dark Souls III",
    "Dark Souls Remastered",
    "Dark Souls II: Scholar of the First Sin",
    "Sekiro",
    "Armored Core VI",
]

PLACEHOLDER_SLOTS = [
    ("Before Malenia",        "2025-06-14  21:32:05"),
    ("After Godfrey",         "2025-06-14  19:11:44"),
    ("RL1 run — Limgrave",    "2025-06-13  15:04:22"),
    ("pre-Radagon",           "2025-06-12  23:58:01"),
    ("Fresh start",           "2025-06-10  10:00:00"),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FromSave Manager")
        self.resize(920, 580)
        self.setMinimumSize(700, 440)

        self._build_ui()
        self._populate_placeholders()
        self.apply_stylesheet()

    # UI construction

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)


        # Inner content with padding
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 12, 14, 10)
        content_layout.setSpacing(10)
        outer.addWidget(content, 1)

        # Top bar
        content_layout.addLayout(self._build_top_bar())

        # Divider
        content_layout.addWidget(_Divider())

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        splitter.addWidget(self._build_slot_panel())
        splitter.addWidget(self._build_info_panel())

        splitter.setSizes([310, 580])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        content_layout.addWidget(splitter, 1)

        # Divider
        content_layout.addWidget(_Divider())

        # Bottom action bar
        content_layout.addLayout(self._build_action_bar())

        # Status bar
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
        self.game_combo.setMinimumWidth(280)
        self.game_combo.setMaximumWidth(380)
        self.game_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bar.addWidget(self.game_combo)

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

        slot_count = QLabel("5 slots")
        slot_count.setObjectName("mutedLabel")
        self.slot_count_label = slot_count
        header.addWidget(slot_count)
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

        # Slot name
        self.detail_name = QLabel("Before Malenia")
        self.detail_name.setObjectName("detailName")
        layout.addWidget(self.detail_name)

        self.detail_time = QLabel("2025-06-14  21:32:05")
        self.detail_time.setObjectName("mutedLabel")
        layout.addWidget(self.detail_time)

        layout.addSpacing(16)

        # Notes
        notes_lbl = QLabel("Notes")
        notes_lbl.setObjectName("fieldLabel")
        layout.addWidget(notes_lbl)
        layout.addSpacing(4)

        self.detail_notes = QLabel("SL 95, pre-Haligtree. All remembrances collected.")
        self.detail_notes.setObjectName("detailNotes")
        self.detail_notes.setWordWrap(True)
        self.detail_notes.setAlignment(Qt.AlignTop)
        layout.addWidget(self.detail_notes)

        layout.addSpacing(24)

        # Game info box
        info_box = QFrame()
        info_box.setObjectName("infoBox")
        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(6)

        info_title = QLabel("Game info")
        info_title.setObjectName("fieldLabel")
        info_layout.addWidget(info_title)

        self.info_save_path = _InfoRow("Save path", "C:\\Users\\You\\AppData\\Roaming\\EldenRing\\")
        self.info_save_file = _InfoRow("Save file", "ER0000.sl2")
        self.info_ro_status = _InfoRow("File status", "Writable")

        for row in (self.info_save_path, self.info_save_file, self.info_ro_status):
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

        # Read-only toggle
        self.ro_btn = QPushButton("  Toggle read-only  (F6)")
        self.ro_btn.setObjectName("ghostBtn")
        self.ro_btn.setCheckable(True)
        self.ro_btn.toggled.connect(self._on_ro_toggled)
        bar.addWidget(self.ro_btn)

        return bar

    # Populate placeholders with dummy data for now, until real data loading is implemented

    def _populate_placeholders(self) -> None:
        for game in PLACEHOLDER_GAMES:
            self.game_combo.addItem(game)

        for name, timestamp in PLACEHOLDER_SLOTS:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, {"name": name, "timestamp": timestamp})
            item.setSizeHint(QSize(0, 52))
            self.slot_list.addItem(item)
            widget = _SlotItem(name, timestamp)
            self.slot_list.setItemWidget(item, widget)

        self.slot_list.setCurrentRow(0)

    # Event handlers

    def _on_slot_selected(self, row: int) -> None:
        if row < 0 or row >= len(PLACEHOLDER_SLOTS):
            return
        name, ts = PLACEHOLDER_SLOTS[row]
        self.detail_name.setText(name)
        self.detail_time.setText(ts)


    def _on_ro_toggled(self, checked: bool) -> None:
        if checked:
            self.ro_btn.setText("Read-only ON  (F6)")
            self.info_ro_status.set_value("Read-only")
            self.status_bar.showMessage("Save file is now read-only.")
        else:
            self.ro_btn.setText("  Toggle read-only  (F6)")
            self.info_ro_status.set_value("✏   Writable")
            self.status_bar.showMessage("Save file is now writable.")


    def _stub(self, action: str):
        """Return a slot that shows a 'not yet implemented' status message."""
        def handler():
            self.status_bar.showMessage(f"[stub] {action} — not yet implemented.")
        return handler


    def apply_stylesheet(self):
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        stylesheet_path = os.path.join(script_dir, 'main_window.qtt')
        
        try:
            with open(stylesheet_path, 'r') as file:
                stylesheet = file.read()
                self.setStyleSheet(stylesheet)
        except FileNotFoundError:
            print(f"Style sheet file not found at: {stylesheet_path}")
            pass

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
        color = "#e8e2d8" if selected else "#d4cfc8"
        bg    = "#1e1e26" if selected else "transparent"
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
