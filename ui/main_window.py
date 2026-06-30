import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer, QFileSystemWatcher, QUrl, QEvent, QPointF
from PySide6.QtGui import QIcon, QKeySequence, QShortcut, QDesktopServices, QPainter, QColor, QPolygonF, QImage
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QListWidget, QListWidgetItem, QLabel,
    QPushButton, QStatusBar, QSplitter, QFrame,
    QSizePolicy, QAbstractItemView, QPlainTextEdit, QInputDialog, QMessageBox, QMenu,
    QLineEdit, QFileDialog, QStackedWidget, QSlider, QScrollArea, QDialog, QCheckBox,
)

import config
import storage
import video as video_module
from hotkeys import GlobalHotkeyListener
from ui.profiles_dialog import ProfilesDialog
from ui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink
    _HAS_MULTIMEDIA = True
except ImportError:
    _HAS_MULTIMEDIA = False

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False


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
        self._actual_video_url: str = ""

        self._notes_save_timer = QTimer(self)
        self._notes_save_timer.setSingleShot(True)
        self._notes_save_timer.setInterval(600)
        self._notes_save_timer.timeout.connect(self._flush_notes)

        self._video_save_timer = QTimer(self)
        self._video_save_timer.setSingleShot(True)
        self._video_save_timer.setInterval(600)
        self._video_save_timer.timeout.connect(self._flush_video)

        self._run_mode = False
        self._run_backup_timer = QTimer(self)
        self._run_backup_timer.setInterval(2 * 60 * 1000)
        self._run_backup_timer.timeout.connect(self._on_run_backup_tick)

        self._guard_watcher = QFileSystemWatcher(self)
        self._guard_watcher.fileChanged.connect(self._on_guarded_file_changed)
        self._guard_slot: Optional[storage.SaveSlot] = None
        self._guard_cfg: Optional[storage.GameConfig] = None

        self._confirm_dialog: Optional[QMessageBox] = None
        self._confirm_action: Optional[str] = None  # "replace" | "delete"
        self._protect_warning_shown: bool = False

        self._global_hotkeys = GlobalHotkeyListener(self)

        self._build_ui()
        self._apply_info_panel()

        # Restore saved window size (minimum is enforced by _sync_minimum_size via timer)
        w, h = self._config.window_width, self._config.window_height
        self.resize(w if w > 0 else 700, h if h > 0 else 580)

        self._global_hotkeys.import_triggered.connect(self._on_import_save)
        self._global_hotkeys.load_triggered.connect(self._on_load_save)
        self._global_hotkeys.replace_triggered.connect(self._on_replace_save)
        self._global_hotkeys.ro_toggle_triggered.connect(self.ro_btn.toggle)
        self._global_hotkeys.next_slot_triggered.connect(self._select_next_slot)
        self._global_hotkeys.prev_slot_triggered.connect(self._select_prev_slot)

        self._load_data()
        self.apply_stylesheet()
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
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 8, 0)
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
        self.detail_notes.setMaximumHeight(90)
        self.detail_notes.textChanged.connect(self._on_notes_changed)
        layout.addWidget(self.detail_notes)

        layout.addSpacing(16)

        video_lbl = QLabel("Video")
        video_lbl.setObjectName("fieldLabel")
        layout.addWidget(video_lbl)
        layout.addSpacing(4)

        video_row = QHBoxLayout()
        video_row.setSpacing(6)
        self.detail_video_url = QLineEdit()
        self.detail_video_url.setObjectName("detailVideoUrl")
        self.detail_video_url.setPlaceholderText("YouTube or direct video URL")
        self.detail_video_url.textChanged.connect(self._on_video_changed)
        video_row.addWidget(self.detail_video_url, 1)

        self.browse_video_btn = QPushButton("Browse")
        self.browse_video_btn.setObjectName("ghostBtn")
        self.browse_video_btn.clicked.connect(self._on_browse_video)
        video_row.addWidget(self.browse_video_btn)

        self.clear_video_btn = QPushButton("Clear")
        self.clear_video_btn.setObjectName("ghostBtn")
        self.clear_video_btn.setEnabled(False)
        self.clear_video_btn.clicked.connect(self._on_clear_video)
        video_row.addWidget(self.clear_video_btn)
        layout.addLayout(video_row)

        self._inline_player = _InlineVideoPlayer()
        self._inline_player.setVisible(False)
        layout.addWidget(self._inline_player)

        layout.addSpacing(16)

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
        self.info_modified = _InfoRow("Modified", "—")
        self.info_file_size = _InfoRow("File size", "—")
        self.info_ro_status = _InfoRow("Practice", "—")

        for row in (self.info_save_path, self.info_created, self.info_modified, self.info_file_size, self.info_ro_status):
            info_layout.addWidget(row)

        layout.addWidget(info_box)
        layout.addStretch()

        scroll.setWidget(panel)
        return scroll

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

        self.ro_btn = QPushButton(_btn_text("Practice Mode", self._config.hotkey_ro_toggle))
        self.ro_btn.setObjectName("ghostBtn")
        self.ro_btn.setCheckable(True)
        self.ro_btn.setEnabled(False)
        self.ro_btn.toggled.connect(self._on_ro_toggled)
        bar.addWidget(self.ro_btn)

        self.run_mode_btn = QPushButton("Run Mode")
        self.run_mode_btn.setObjectName("ghostBtn")
        self.run_mode_btn.setCheckable(True)
        self.run_mode_btn.setToolTip(
            "Disables Load Save and Practice Mode to protect the game save,\n"
            "and takes a rolling backup every 2 minutes (keeps last 3)."
        )
        self.run_mode_btn.toggled.connect(self._on_run_mode_toggled)
        bar.addWidget(self.run_mode_btn)

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
        self.info_save_path.setVisible(not self._config.hide_paths)
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
        self.info_save_path.setVisible(not self._config.hide_paths)
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
        compact = True
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

        compact = True
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

    def _select_next_slot(self) -> None:
        row = self.slot_list.currentRow()
        if row < self.slot_list.count() - 1:
            self.slot_list.setCurrentRow(row + 1)

    def _select_prev_slot(self) -> None:
        row = self.slot_list.currentRow()
        if row > 0:
            self.slot_list.setCurrentRow(row - 1)

    # Event handlers

    def _on_slot_selected(self, row: int) -> None:
        self._flush_notes()
        self._flush_video()
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
        self._set_video_url(slot.video_url)
        self.info_created.set_value(_fmt_dt(slot.date_created))
        self.info_modified.set_value(_fmt_dt(slot.date_modified) if slot.date_modified else "—")
        size = _slot_save_size(slot)
        self.info_file_size.set_value(_fmt_size(size) if size is not None else "—")
        save_files = _slot_save_files(slot)
        if save_files:
            is_guarded = (self._guard_slot is not None
                          and self._guard_slot.path == slot.path)
            self.info_ro_status.set_value("Active" if is_guarded else "Inactive")
            self.ro_btn.blockSignals(True)
            self.ro_btn.setChecked(is_guarded)
            self.ro_btn.setText(self._ro_btn_text(is_guarded))
            self.ro_btn.blockSignals(False)
            self.ro_btn.setEnabled(not self._run_mode)
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
        self._set_video_url("")
        self.info_created.set_value("—")
        self.info_modified.set_value("—")
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
        if not self._current_slot.path.exists():
            return
        storage.save_notes(self._current_slot, self.detail_notes.toPlainText())
        self.status_bar.showMessage("Notes saved.", 2000)

    def _set_video_url(self, url: str) -> None:
        self._actual_video_url = url
        parsed = QUrl(url.strip()) if url.strip() else QUrl()
        display = Path(parsed.toLocalFile()).name if parsed.isLocalFile() else url
        self.detail_video_url.blockSignals(True)
        self.detail_video_url.setText(display)
        self.detail_video_url.blockSignals(False)
        has_url = bool(url.strip())
        self.clear_video_btn.setEnabled(has_url)
        if has_url:
            self._inline_player.load(url.strip())
            self._inline_player.setVisible(True)
            QTimer.singleShot(50, self.update)
        else:
            self._inline_player.unload()
            self._inline_player.setVisible(False)
        QTimer.singleShot(0, self._sync_minimum_size)

    def _on_video_changed(self) -> None:
        text = self.detail_video_url.text().strip()
        if not QUrl(text).isLocalFile():
            self._actual_video_url = text
        self.clear_video_btn.setEnabled(bool(self._actual_video_url))
        self._video_save_timer.start()

    def _flush_video(self) -> None:
        self._video_save_timer.stop()
        if self._current_slot is None:
            return
        if not self._current_slot.path.exists():
            return
        url = self._actual_video_url
        if url != self._current_slot.video_url:
            storage.save_video_url(self._current_slot, url)
            self.status_bar.showMessage("Video link saved.", 2000)
        self._set_video_url(url)

    def _on_browse_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select video file", "",
            "Video files (*.mp4 *.webm *.ogg *.mov *.m4v *.mkv);;All files (*)",
        )
        if path:
            self._set_video_url(QUrl.fromLocalFile(path).toString())
            self._video_save_timer.start()

    def _on_clear_video(self) -> None:
        self._inline_player.unload()
        self._inline_player.setVisible(False)
        self.detail_video_url.clear()
        self._flush_video()
        QTimer.singleShot(0, self._sync_minimum_size)

    def _on_ro_toggled(self, checked: bool) -> None:
        if checked and self._run_mode:
            self.ro_btn.blockSignals(True)
            self.ro_btn.setChecked(False)
            self.ro_btn.blockSignals(False)
            self.status_bar.showMessage("Run mode is on — disable it before using Practice Mode.")
            return
        warning_shown = False
        if checked and not self._config.protect_warning_acknowledged and not self._protect_warning_shown:
            if not self._show_protect_warning():
                self.ro_btn.blockSignals(True)
                self.ro_btn.setChecked(False)
                self.ro_btn.blockSignals(False)
                return
            warning_shown = True
        if checked and not warning_shown and self._config.confirm_lock_slot:
            if not self._confirm("lock", "Practice Mode",
                                 "Enable practice mode?\n\nThis will immediately overwrite the game's current save with this slot and keep restoring it any time the game tries to save. The game will not be able to save progress while practice mode is on.",
                                 disable_key="confirm_lock_slot"):
                self.ro_btn.blockSignals(True)
                self.ro_btn.setChecked(False)
                self.ro_btn.blockSignals(False)
                return
        if not self._current_slot:
            return
        save_files = _slot_save_files(self._current_slot)
        if not save_files:
            return
        game_cfg = self._get_game_cfg()
        if not game_cfg:
            return

        if checked:
            self._guard_slot = self._current_slot
            self._guard_cfg = game_cfg
            try:
                storage.snapshot_practice_start(self._guard_cfg)
                storage.load_save(self._guard_slot, self._guard_cfg, make_backup=False)
            except OSError as e:
                logger.exception("Practice Mode: failed to apply slot on activate: slot=%r", self._current_slot.name)
                self.status_bar.showMessage(f"Practice Mode: failed to apply — {e}")
                self._guard_slot = None
                self._guard_cfg = None
                self.ro_btn.blockSignals(True)
                self.ro_btn.setChecked(False)
                self.ro_btn.blockSignals(False)
                return
            live_paths = [str(f) for f in _live_game_files(game_cfg)]
            if live_paths:
                self._guard_watcher.addPaths(live_paths)
        else:
            self._guard_slot = None
            self._guard_cfg = None
            watched = self._guard_watcher.files()
            if watched:
                self._guard_watcher.removePaths(watched)

        n = len(save_files)
        label = save_files[0].name if n == 1 else f"{n} files"
        self.ro_btn.setText(self._ro_btn_text(checked))
        self.info_ro_status.set_value("Active" if checked else "Inactive")
        self.status_bar.showMessage(
            f"'{label}' — {'practice mode is on.' if checked else 'practice mode is off.'}"
        )

    def _show_protect_warning(self) -> bool:
        """Show the protect-save warning. Returns True if the user confirmed, False if cancelled."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Practice Mode — heads up")
        dlg.setMinimumWidth(420)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 16)

        msg = QLabel(
            "<b>Enabling practice mode immediately overwrites the game's current save with the "
            "selected slot, then keeps restoring it any time the game tries to change it.</b><br><br>"
            "Your current save is kept as a backup before the overwrite. The game will not be able to "
            "save progress while practice mode is on — any new save data the game tries to write "
            "will be lost. Disable practice mode before saving in-game.<br><br>"
            "This feature may not work correctly on all games, behaviour depends on how the "
            "game handles save files and has not been tested with every title."
        )
        msg.setWordWrap(True)
        msg.setTextFormat(Qt.RichText)
        layout.addWidget(msg)

        never_checkbox = QCheckBox("Don't show this again")
        layout.addWidget(never_checkbox)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        confirm_btn = QPushButton("Got it")
        confirm_btn.setObjectName("primaryBtn")
        confirm_btn.setDefault(True)
        btn_row.addWidget(confirm_btn)
        layout.addLayout(btn_row)

        def _on_confirm():
            if never_checkbox.isChecked():
                self._config.protect_warning_acknowledged = True
                import config as _cfg_mod
                _cfg_mod.save_config(self._config)
            else:
                self._protect_warning_shown = True
            dlg.accept()

        confirm_btn.clicked.connect(_on_confirm)
        return dlg.exec() == QDialog.Accepted

    def _on_guarded_file_changed(self, path: str) -> None:
        if self._guard_slot is None or self._guard_cfg is None:
            return
        # Remove the path now so our own restore write doesn't re-trigger this handler
        self._guard_watcher.removePath(path)
        # Delay the restore so the game has time to finish its write and close the file
        QTimer.singleShot(500, lambda: self._do_guard_restore(path))

    def _do_guard_restore(self, path: str) -> None:
        if self._guard_slot is None or self._guard_cfg is None:
            return
        try:
            storage.load_save(self._guard_slot, self._guard_cfg, make_backup=False)
            self.status_bar.showMessage(
                f"Protected: restored '{self._guard_slot.name}'.", 4000
            )
        except OSError as e:
            logger.exception("Lock restore failed: slot=%r path=%s", self._guard_slot.name, path)
            self.status_bar.showMessage(f"Lock: restore failed — {e}")
        # Re-add after our write is done so the next game save is caught
        self._guard_watcher.addPath(path)

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
            logger.exception("Import save failed: game=%r profile=%r slot=%r",
                             self.game_combo.currentText(), profile, name)
            self.status_bar.showMessage(f"Import failed: {e}")
            return
        self._reload_slots(name)
        self.status_bar.showMessage(f"Imported '{name}'.")

    def _confirm(self, action: str, title: str, message: str,
                 disable_key: Optional[str] = None) -> bool:
        """Show a Yes/No dialog, allowing the same hotkey to confirm it.

        If a dialog for the same action is already open, accepts it and returns
        False (the first pending call will proceed). If a *different* dialog is
        open, does nothing and returns False.

        If disable_key is provided, a "Don't ask again" checkbox is shown. When
        checked on confirm, the corresponding Config field is set to False and saved.
        """
        if self._confirm_dialog is not None:
            if self._confirm_action == action:
                btn = self._confirm_dialog.button(QMessageBox.Yes)
                if btn:
                    btn.click()
            return False

        dlg = QMessageBox(self)
        dlg.setWindowTitle(title)
        dlg.setText(message)
        dlg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dlg.setDefaultButton(QMessageBox.No)

        checkbox: Optional[QCheckBox] = None
        if disable_key:
            checkbox = QCheckBox("Don't ask again")
            dlg.setCheckBox(checkbox)

        self._confirm_dialog = dlg
        self._confirm_action = action
        result = dlg.exec()
        self._confirm_dialog = None
        self._confirm_action = None

        confirmed = result == QMessageBox.Yes
        if confirmed and checkbox is not None and checkbox.isChecked():
            setattr(self._config, disable_key, False)
            config.save_config(self._config)

        return confirmed

    def _on_replace_save(self) -> None:
        row = self.slot_list.currentRow()
        if row < 0 or row >= len(self._slots):
            self.status_bar.showMessage("No slot selected.")
            return
        cfg = self._get_game_cfg()
        if not cfg or not self._validate_game_save_path(cfg):
            return
        slot = self._slots[row]
        if self._guard_slot is not None and self._guard_slot.path == slot.path:
            self.status_bar.showMessage(f"'{slot.name}' has practice mode active — disable it before replacing.")
            return
        if self._config.confirm_replace:
            if not self._confirm("replace", "Replace save",
                                 f"Overwrite '{slot.name}' with the current game save?\n\nThis cannot be undone.",
                                 disable_key="confirm_replace"):
                return
        slot_name = slot.name
        try:
            storage.replace_save(slot, cfg)
        except Exception as e:
            logger.exception("Replace save failed: game=%r profile=%r slot=%r",
                             slot.game, slot.profile, slot.name)
            self.status_bar.showMessage(f"Replace failed: {e}")
            return
        self._reload_slots(slot_name)
        self.status_bar.showMessage(f"Replaced '{slot_name}'.")

    def _on_load_save(self) -> None:
        if self._run_mode:
            self.status_bar.showMessage("Run mode is on — disable it before loading a save.")
            return
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
            logger.exception("Load save failed: game=%r profile=%r slot=%r",
                             slot.game, slot.profile, slot.name)
            self.status_bar.showMessage(f"Load failed: {e}")
            return

        # If protection is active, re-point the guard at the newly loaded slot
        if self._guard_cfg is not None and self._guard_cfg.name == cfg.name:
            self._guard_slot = slot
            # Watcher paths stay the same (same game, same live files)

        self.status_bar.showMessage(f"Loaded '{slot.name}' to game save.")

    def _on_delete_slot(self) -> None:
        row = self.slot_list.currentRow()
        if row < 0 or row >= len(self._slots):
            self.status_bar.showMessage("No slot selected.")
            return
        slot = self._slots[row]
        soft = self._config.soft_delete
        if self._config.confirm_delete:
            msg = (f"Move '{slot.name}' to trash?" if soft
                   else f"Permanently delete '{slot.name}'?\n\nThis cannot be undone.")
            if not self._confirm("delete", "Delete slot", msg, disable_key="confirm_delete"):
                return
        self._flush_notes()
        self._flush_video()
        self._current_slot = None
        try:
            storage.delete_slot(slot, soft=soft)
        except Exception as e:
            logger.exception("Delete slot failed: game=%r profile=%r slot=%r soft=%s",
                             slot.game, slot.profile, slot.name, soft)
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
        self._flush_video()
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
            logger.exception("Rename slot failed: game=%r profile=%r %r -> %r",
                             slot.game, slot.profile, slot.name, name)
            self.status_bar.showMessage(f"Rename failed: {e}")
            return
        game_name = self.game_combo.currentText()
        profile_name = self.profile_combo.currentText()
        # Keep order.json in sync whenever it already exists, so the renamed slot
        # stays in position even if the user is not currently in Custom sort mode.
        if self._config.slot_sort == "custom" or storage.load_slot_order(game_name, profile_name):
            storage.save_slot_order(game_name, profile_name, [s.name for s in self._slots])
        self._reload_slots(name)
        self.status_bar.showMessage(f"Renamed to '{name}'.")

    def _on_slot_context_menu(self, pos) -> None:
        item = self.slot_list.itemAt(pos)
        if not item:
            return
        row = self.slot_list.row(item)
        self.slot_list.setCurrentRow(row)

        menu = QMenu(self)
        menu.addAction("Rename", self._on_rename_slot)
        menu.addAction("Load save", self._on_load_save)
        if self._current_slot and self._current_slot.video_url.strip():
            url = self._current_slot.video_url.strip()
            menu.addAction("Open video in browser", lambda: QDesktopServices.openUrl(QUrl(url)))
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
            logger.exception("Duplicate slot failed: game=%r profile=%r slot=%r",
                             slot.game, slot.profile, slot.name)
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
            logger.exception("Copy slot to profile failed: game=%r %r/%r -> %r/%r",
                             slot.game, slot.profile, slot.name, target_profile, new_name)
            self.status_bar.showMessage(f"{verb} failed: {e}")
            return

        slot_name = slot.name
        if move:
            self._flush_notes()
            self._flush_video()
            self._current_slot = None
            try:
                storage.delete_slot(slot, soft=self._config.soft_delete)
            except Exception as e:
                logger.exception("Move: delete after copy failed: game=%r %r/%r -> %r",
                                 slot.game, current_profile, slot_name, target_profile)
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

    def _on_run_mode_toggled(self, on: bool) -> None:
        self._run_mode = on
        self.load_btn.setEnabled(not on)
        if on:
            if self.ro_btn.isChecked():
                self.ro_btn.setChecked(False)
            self.ro_btn.setEnabled(False)
            self._run_backup_timer.start()
            self._on_run_backup_tick()
            self.status_bar.showMessage(
                "Run mode on — load and lock disabled, backing up every 2 min.", 5000
            )
        else:
            self._run_backup_timer.stop()
            if self._current_slot and _slot_save_files(self._current_slot):
                self.ro_btn.setEnabled(True)
            self.status_bar.showMessage("Run mode off.", 3000)

    def _on_run_backup_tick(self) -> None:
        cfg = self._get_game_cfg()
        if not cfg:
            return
        try:
            storage.take_run_backup(cfg)
            self.status_bar.showMessage("Run backup saved.", 2000)
        except Exception as e:
            logger.exception("Run backup failed: game=%r", cfg.name)
            self.status_bar.showMessage(f"Run backup failed: {e}", 3000)

    def show_first_run_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("No settings found")
        dlg.setMinimumWidth(380)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 16)

        msg = QLabel(
            "No settings found. Would you like to configure the application?<br><br>"
            "You'll need to add your games and their save file paths before you can get started."
        )
        msg.setWordWrap(True)
        msg.setTextFormat(Qt.RichText)
        layout.addWidget(msg)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        later_btn = QPushButton("Maybe later")
        later_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(later_btn)
        open_btn = QPushButton("Open Settings")
        open_btn.setObjectName("primaryBtn")
        open_btn.setDefault(True)
        open_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(open_btn)
        layout.addLayout(btn_row)

        if dlg.exec() == QDialog.Accepted:
            self._on_open_settings()

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
        logger.info("Settings saved by user")

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
            self.info_save_path.setVisible(not self._config.hide_paths)
            self.info_save_path.set_value(_game_path_display(game_cfg))

            self._reload_slots(prev_slot)
        else:
            self.profile_combo.blockSignals(True)
            self.profile_combo.clear()
            self.profile_combo.blockSignals(False)
            self._reload_slots()

        self._apply_info_panel()
        self._apply_hotkeys()
        self.status_bar.showMessage("Settings saved.")

    def _ro_btn_text(self, is_on: bool) -> str:
        key = _hotkey_label(self._config.hotkey_ro_toggle)
        if is_on:
            return _btn_text("Practicing", key)
        return _btn_text("Practice Mode", key)

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
        self.import_btn.setText(_btn_text("Import Save", cfg.hotkey_import))
        self.load_btn.setText(_btn_text("Load Save", cfg.hotkey_load))
        self.replace_btn.setText(_btn_text("Replace Save", cfg.hotkey_replace))
        self.ro_btn.setText(self._ro_btn_text(self.ro_btn.isChecked()))

        started = self._global_hotkeys.start(
            cfg.hotkey_import, cfg.hotkey_load, cfg.hotkey_replace, cfg.hotkey_ro_toggle,
            cfg.hotkey_next_slot, cfg.hotkey_prev_slot,
            enabled=cfg.global_hotkeys_enabled,
        )
        if not started:
            # pynput unavailable (e.g. macOS without Accessibility permission) or global hotkeys
            # disabled — fall back to in-app QShortcuts. When pynput IS running it fires on both
            # focused and unfocused presses, so QShortcuts must not be added or they double-trigger.
            _bind(cfg.hotkey_import, self._on_import_save)
            _bind(cfg.hotkey_load, self._on_load_save)
            _bind(cfg.hotkey_replace, self._on_replace_save)
            _bind(cfg.hotkey_ro_toggle, self.ro_btn.toggle)
            _bind(cfg.hotkey_next_slot, self._select_next_slot)
            _bind(cfg.hotkey_prev_slot, self._select_prev_slot)
            global_keys = [cfg.hotkey_import, cfg.hotkey_load, cfg.hotkey_replace, cfg.hotkey_ro_toggle]
            if cfg.global_hotkeys_enabled and any(global_keys):
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
                path_str = "(path hidden)" if self._config.hide_paths else missing[0]
                self.status_bar.showMessage(f"Save file not found: {path_str}")
                return False
            return True
        if not cfg.save_path:
            self.status_bar.showMessage("Save path is not configured for this game.")
            return False
        src = Path(cfg.save_path)
        if not src.exists():
            path_str = "(path hidden)" if self._config.hide_paths else str(src)
            self.status_bar.showMessage(f"Save path not found: {path_str}")
            return False
        return True

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._inline_player.update_height(self.height())

    def closeEvent(self, event) -> None:
        logger.info("Application closing: game=%r profile=%r slot=%r",
                    self.game_combo.currentText(),
                    self.profile_combo.currentText(),
                    self._current_slot.name if self._current_slot else "")
        self._run_backup_timer.stop()
        self._global_hotkeys.stop()
        self._flush_notes()
        self._flush_video()
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
            logger.warning("Stylesheet not found: %s", stylesheet_path)


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


def _live_game_files(game_cfg: storage.GameConfig) -> list[Path]:
    """Return the game's live save paths that should be watched for protection."""
    if game_cfg.save_mode == "file":
        return [Path(game_cfg.save_path)]
    if game_cfg.save_mode == "files":
        return [Path(p) for p in game_cfg.save_paths]
    if game_cfg.save_mode == "folder":
        folder = Path(game_cfg.save_path)
        if folder.exists():
            return [f for f in folder.rglob("*") if f.is_file()]
    return []


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


class _ResizeHandle(QWidget):
    _MIN_H = 120

    def __init__(self, target: QWidget, on_resize=None, parent=None):
        super().__init__(parent)
        self._target = target
        self._on_resize = on_resize
        self._drag_y = 0.0
        self._drag_h = 0
        self.setFixedHeight(5)
        self.setCursor(Qt.SizeVerCursor)
        self.setStyleSheet("background: #2a2a3a;")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_y = event.globalPosition().y()
            self._drag_h = self._target.height()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().y() - self._drag_y
            new_h = max(self._MIN_H, self._drag_h + int(delta))
            self._target.setFixedHeight(new_h)
            if self._on_resize:
                self._on_resize(new_h)
            event.accept()


class _InlineVideoPlayer(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._url = ""
        self._player = None
        self._audio = None
        self._seeking = False
        self._thumb_player = None
        self._thumb_sink = None
        self._main_sink = None

        self._user_height: int = 0
        self.setFocusPolicy(Qt.ClickFocus)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 0)
        outer.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setMinimumHeight(120)
        self._stack.setFixedHeight(320)

        if _HAS_MULTIMEDIA:
            self._video_widget = _VideoFrame()
            self._video_widget.installEventFilter(self)
        else:
            self._video_widget = QWidget()
            self._video_widget.setStyleSheet("background: #000;")

        self._video_container = QWidget()
        vc_layout = QVBoxLayout(self._video_container)
        vc_layout.setContentsMargins(0, 0, 0, 0)
        vc_layout.setSpacing(0)
        vc_layout.addWidget(self._video_widget)
        self._play_overlay = _PlayOverlay(self._toggle, self._video_container)
        self._play_overlay.hide()
        self._video_container.installEventFilter(self)

        self._stack.addWidget(self._video_container)  # index 0: local

        if _HAS_WEBENGINE:
            self._web_view = QWebEngineView()
        else:
            self._web_view = QWidget()
            self._web_view.setStyleSheet("background: #000;")
        self._stack.addWidget(self._web_view)  # index 1: web

        outer.addWidget(self._stack, 1)

        # Controls for local video
        self._local_bar = QWidget()
        self._local_bar.setStyleSheet("background: #16161e;")
        local_ctrl = QVBoxLayout(self._local_bar)
        local_ctrl.setContentsMargins(8, 4, 8, 4)
        local_ctrl.setSpacing(3)

        self._seek = QSlider(Qt.Horizontal)
        self._seek.setRange(0, 0)
        self._seek.sliderPressed.connect(self._on_seek_pressed)
        self._seek.sliderMoved.connect(self._on_seek_moved)
        self._seek.sliderReleased.connect(self._on_seek_released)
        local_ctrl.addWidget(self._seek)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        _ui_dir = Path(__file__).parent
        self._icon_play = QIcon(str(_ui_dir / "play.svg"))
        self._icon_pause = QIcon(str(_ui_dir / "pause.svg"))
        self._play_btn = QPushButton()
        self._play_btn.setIcon(self._icon_play)
        self._play_btn.setIconSize(QSize(14, 14))
        self._play_btn.setObjectName("ghostBtn")
        self._play_btn.clicked.connect(self._toggle)
        btn_row.addWidget(self._play_btn)

        self._time_lbl = QLabel("0:00 / 0:00")
        self._time_lbl.setStyleSheet("color: #888899; font-size: 11px;")
        btn_row.addWidget(self._time_lbl)

        btn_row.addStretch()

        self._vol = QSlider(Qt.Horizontal)
        self._vol.setRange(0, 100)
        self._vol.setValue(100)
        self._vol.setFixedWidth(64)
        self._vol.valueChanged.connect(self._set_volume)
        btn_row.addWidget(self._vol)

        browser_btn = QPushButton("Open in player")
        browser_btn.setObjectName("ghostBtn")
        browser_btn.clicked.connect(self._open_in_browser)
        btn_row.addWidget(browser_btn)

        local_ctrl.addLayout(btn_row)
        outer.addWidget(self._local_bar)

        # Bar for web video (open in browser)
        self._web_bar = QWidget()
        self._web_bar.setStyleSheet("background: #16161e;")
        web_row = QHBoxLayout(self._web_bar)
        web_row.setContentsMargins(8, 6, 8, 6)
        web_row.addStretch()
        web_browser_btn = QPushButton("Open in browser")
        web_browser_btn.setObjectName("ghostBtn")
        web_browser_btn.clicked.connect(self._open_web_in_browser)
        web_row.addWidget(web_browser_btn)
        outer.addWidget(self._web_bar)
        outer.addWidget(_ResizeHandle(self._stack, on_resize=self._on_manual_resize))

        self._local_bar.hide()
        self._web_bar.hide()

    def _on_manual_resize(self, h: int) -> None:
        self._user_height = h

    def update_height(self, win_h: int) -> None:
        if self._user_height != 0:
            return
        new_h = max(120, int(win_h * 0.50))
        if abs(self._stack.height() - new_h) > 2:
            self._stack.setFixedHeight(new_h)

    def load(self, url: str) -> None:
        self._stop()
        self._url = url
        if not url:
            return
        parsed = QUrl(url)
        if parsed.isLocalFile():
            self._load_local(parsed)
        else:
            self._load_web(url)

    def unload(self) -> None:
        self._stop()
        if _HAS_WEBENGINE:
            self._web_view.load(QUrl("about:blank"))
        self._url = ""

    def _load_local(self, parsed: QUrl) -> None:
        if not _HAS_MULTIMEDIA:
            return
        if _HAS_WEBENGINE:
            self._web_view.load(QUrl("about:blank"))
        self._stack.setCurrentIndex(0)
        self._local_bar.show()
        self._web_bar.hide()
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(self._vol.value() / 100.0)
        self._player.setAudioOutput(self._audio)
        self._main_sink = QVideoSink(self)
        self._main_sink.videoFrameChanged.connect(self._video_widget.update_frame)
        self._player.setVideoSink(self._main_sink)
        self._player.setSource(parsed)
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        self._play_overlay.set_thumbnail(None)
        self._play_overlay.setGeometry(self._video_container.rect())
        self._play_overlay.show()
        self._play_overlay.raise_()
        self._grab_thumbnail(parsed)

    def _load_web(self, url: str) -> None:
        if not _HAS_WEBENGINE:
            return
        self._stack.setCurrentIndex(1)
        self._local_bar.hide()
        self._web_bar.show()
        html = video_module.embed_html(url, autoplay=False) or video_module.unsupported_html()
        self._web_view.setHtml(html, QUrl("http://localhost/"))

    def _stop(self) -> None:
        if self._thumb_player is not None:
            self._thumb_player.stop()
            self._thumb_player.deleteLater()
            self._thumb_player = None
        if self._thumb_sink is not None:
            self._thumb_sink.deleteLater()
            self._thumb_sink = None
        if self._player is not None:
            self._player.positionChanged.disconnect(self._on_position)
            self._player.durationChanged.disconnect(self._on_duration)
            self._player.playbackStateChanged.disconnect(self._on_state)
            self._player.stop()
            self._player.deleteLater()
            self._player = None
        if self._main_sink is not None:
            self._main_sink.deleteLater()
            self._main_sink = None
        if self._audio is not None:
            self._audio.deleteLater()
            self._audio = None
        self._play_overlay.hide()
        self._seeking = False
        self._seek.blockSignals(True)
        self._seek.setValue(0)
        self._seek.setRange(0, 0)
        self._seek.blockSignals(False)
        self._time_lbl.setText("0:00 / 0:00")
        self._play_btn.setIcon(self._icon_play)
        self._local_bar.hide()
        self._web_bar.hide()

    def _grab_thumbnail(self, url: QUrl) -> None:
        if not _HAS_MULTIMEDIA:
            return
        self._thumb_player = QMediaPlayer(self)
        self._thumb_sink = QVideoSink(self)
        self._thumb_player.setVideoSink(self._thumb_sink)
        self._thumb_player.setSource(url)
        state = {"seeked": False}

        def on_frame(frame) -> None:
            if self._thumb_player is None or not frame.isValid():
                return
            if not state["seeked"]:
                dur = self._thumb_player.duration()
                if dur > 1000:
                    self._thumb_player.setPosition(min(2000, dur // 4))
                state["seeked"] = True
                return
            img = frame.toImage()
            if img.isNull():
                return
            tp, ts = self._thumb_player, self._thumb_sink
            self._thumb_player = None
            self._thumb_sink = None
            tp.stop()
            tp.deleteLater()
            ts.deleteLater()
            self._play_overlay.set_thumbnail(img)

        self._thumb_sink.videoFrameChanged.connect(on_frame)
        self._thumb_player.play()

    def _open_in_browser(self) -> None:
        if self._player is not None:
            self._player.pause()
        QDesktopServices.openUrl(QUrl(self._url))

    def eventFilter(self, obj, event) -> bool:
        if obj is self._video_widget and event.type() == QEvent.Type.MouseButtonRelease:
            self._toggle()
            self.setFocus()
            return True
        if obj is self._video_container and event.type() == QEvent.Type.Resize:
            self._play_overlay.setGeometry(obj.rect())
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._toggle()
            event.accept()
            return
        super().keyPressEvent(event)

    def _open_web_in_browser(self) -> None:
        if not _HAS_WEBENGINE:
            QDesktopServices.openUrl(QUrl(self._url))
            return
        self._web_view.page().runJavaScript(
            "(function(){"
            "var f=document.querySelector('iframe');if(!f)return;"
            "f.contentWindow.postMessage('{\"event\":\"command\",\"func\":\"pauseVideo\",\"args\":\"\"}','*');"
            "f.contentWindow.postMessage('{\"method\":\"pause\"}','*');"
            "})()"
        )
        self._web_view.page().runJavaScript(
            "window._embed_time||0",
            self._open_browser_at_time,
        )

    def _open_browser_at_time(self, t) -> None:
        url = self._url
        if isinstance(t, (int, float)) and t > 1 and video_module.youtube_video_id(url):
            sep = '&' if '?' in url else '?'
            url = f"{url}{sep}t={int(t)}"
        QDesktopServices.openUrl(QUrl(url))

    def _toggle(self) -> None:
        if self._player is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_seek_pressed(self) -> None:
        self._seeking = True

    def _on_seek_moved(self, ms: int) -> None:
        dur = self._player.duration() if self._player is not None else 0
        self._time_lbl.setText(f"{_fmt_ms(ms)} / {_fmt_ms(dur)}")
        if self._player is not None:
            self._player.setPosition(ms)

    def _on_seek_released(self) -> None:
        self._seeking = False
        if self._player is not None:
            self._player.setPosition(self._seek.value())

    def _set_volume(self, v: int) -> None:
        if self._audio is not None:
            self._audio.setVolume(v / 100.0)

    def _on_position(self, ms: int) -> None:
        if not self._seeking:
            self._seek.blockSignals(True)
            self._seek.setValue(ms)
            self._seek.blockSignals(False)
            dur = self._player.duration() if self._player is not None else 0
            self._time_lbl.setText(f"{_fmt_ms(ms)} / {_fmt_ms(dur)}")

    def _on_duration(self, ms: int) -> None:
        self._seek.setRange(0, ms)

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._play_btn.setIcon(self._icon_pause if playing else self._icon_play)
        if playing:
            self._play_overlay.hide()


class _PlayOverlay(QWidget):
    def __init__(self, on_click, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._on_click = on_click
        self._thumbnail: QImage | None = None

    def set_thumbnail(self, img: QImage | None) -> None:
        self._thumbnail = img
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._thumbnail is not None and not self._thumbnail.isNull():
            scaled = self._thumbnail.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawImage(x, y, scaled)
            p.fillRect(self.rect(), QColor(0, 0, 0, 60))
        cx = self.width() / 2
        cy = self.height() / 2
        r = 36.0
        p.setBrush(QColor(255, 255, 255, 200))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)
        tri_h = r * 0.85
        tri_w = tri_h * 0.9
        ox = r * 0.12
        p.setBrush(QColor(20, 20, 20, 220))
        p.drawPolygon(QPolygonF([
            QPointF(cx - tri_w / 2 + ox, cy - tri_h / 2),
            QPointF(cx - tri_w / 2 + ox, cy + tri_h / 2),
            QPointF(cx + tri_w / 2 + ox, cy),
        ]))


class _VideoFrame(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: #000;")
        self._frame: QImage | None = None

    def update_frame(self, frame) -> None:
        if frame.isValid():
            img = frame.toImage()
            if not img.isNull():
                self._frame = img
                self.update()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        if self._frame and not self._frame.isNull():
            scaled = self._frame.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawImage(x, y, scaled)


def _fmt_ms(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02}:{s:02}"
    return f"{m}:{s:02}"
