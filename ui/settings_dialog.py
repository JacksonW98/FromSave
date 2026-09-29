import dataclasses
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QGroupBox, QHBoxLayout, QKeySequenceEdit, QLabel,
    QLineEdit, QMessageBox, QPushButton, QRadioButton, QScrollArea, QSlider, QVBoxLayout,
    QWidget,
)

import api_server
import config
import storage
from ui.add_game_dialog import AddGameDialog
from ui.save_path_widgets import browse_save_path, set_path_input_mode, split_paths
from ui.update_flow import UpdateFlow
from version import __version__

_MAIN_HOTKEYS = (
    ("hotkey_import", "Import save"),
    ("hotkey_load", "Load save"),
    ("hotkey_replace", "Replace save"),
    ("hotkey_ro_toggle", "Practice Mode"),
    ("hotkey_next_slot", "Next slot"),
    ("hotkey_prev_slot", "Previous slot"),
)

_OVERLAY_HOTKEYS = (
    ("overlay_hotkey_import", "Import save"),
    ("overlay_hotkey_load", "Load save"),
    ("overlay_hotkey_replace", "Replace save"),
    ("overlay_hotkey_rename", "Rename current save"),
    ("overlay_hotkey_ro_toggle", "Practice Mode"),
    ("overlay_hotkey_next_slot", "Next slot"),
    ("overlay_hotkey_prev_slot", "Previous slot"),
)


class _NoScrollComboBox(QComboBox):
    """Ignores the mouse wheel so scrolling the settings panel can't change it."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class _NoScrollSlider(QSlider):
    """Ignores the mouse wheel so scrolling the settings panel can't change it."""

    def wheelEvent(self, event) -> None:
        event.ignore()


@dataclass
class _GameRow:
    name: str
    mode: str
    widget: QWidget
    mode_combo: QComboBox
    edit: QLineEdit
    browse_btn: QPushButton
    reveal_btn: QPushButton

    def to_config(self) -> storage.GameConfig:
        if self.mode == "files":
            return storage.GameConfig(self.name, "", "files", split_paths(self.edit.text()))
        return storage.GameConfig(self.name, self.edit.text().strip(), self.mode)


class SettingsDialog(QDialog):
    """Edits a copy of the config and game list; read the results after exec().

    The companion checkbox is the exception: it applies immediately through
    on_companion_toggle (which returns the pairing code), since it controls a live server.
    """

    def __init__(self, cfg: config.Config, games: list[storage.GameConfig], parent=None,
                 on_companion_toggle=None, on_companion_notice_shown=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(620)
        self.setMaximumHeight(700)
        self._on_companion_toggle = on_companion_toggle
        self._on_companion_notice_shown = on_companion_notice_shown
        self._companion_info_visible = False
        self._cfg = dataclasses.replace(cfg)
        self._checkboxes: dict[str, QCheckBox] = {}
        self._hotkey_edits: dict[str, QKeySequenceEdit] = {}
        self._game_rows: list[_GameRow] = []
        self._removed_game_names: list[str] = []

        self._build_ui()
        self._update_flow = UpdateFlow(self)
        self._update_flow.status_changed.connect(self._update_status_lbl.setText)
        self._update_flow.finished.connect(lambda: self._check_updates_btn.setEnabled(True))
        for game in games:
            self._add_game_row(game.name, game.save_mode,
                               "; ".join(game.save_paths) if game.save_mode == "files" else game.save_path)
        self._apply_path_hide()
        self._initial_values = self._form_values()
        self._initial_games = self.result_games

        ui_dir = Path(__file__).resolve().parent
        qss = (ui_dir / "settings_dialog.qss").read_text()
        self.setStyleSheet(qss.replace("{ui_dir}", ui_dir.as_posix()))

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

        layout.addWidget(self._build_updates_box())
        layout.addWidget(self._build_companion_box())

        behaviour_box = QGroupBox("Behaviour")
        behaviour_layout = QVBoxLayout(behaviour_box)
        self._add_checkbox(behaviour_layout, "confirm_replace", "Confirm before replacing a save")
        self._add_checkbox(behaviour_layout, "confirm_delete", "Confirm before deleting a save")
        self._add_checkbox(behaviour_layout, "confirm_lock_slot", "Confirm before enabling practice mode")
        self._add_checkbox(behaviour_layout, "soft_delete",
                           "Send deleted saves to the system trash instead of permanently deleting")
        self._add_checkbox(behaviour_layout, "hide_details",
                           "Hide details panel  (slot name, notes, and game info)")
        self._add_checkbox(behaviour_layout, "hide_paths", "Hide file paths").toggled.connect(
            self._apply_path_hide
        )
        layout.addWidget(behaviour_box)

        naming_box = QGroupBox("Import naming")
        naming_layout = QVBoxLayout(naming_box)
        naming_layout.setSpacing(10)
        prompt_name = QRadioButton("Always prompt for a name")
        self._auto_name = QRadioButton('Auto-name  (e.g. "new save", "new save 2"…)')
        (self._auto_name if self._cfg.auto_name_imports else prompt_name).setChecked(True)
        naming_layout.addWidget(prompt_name)
        naming_layout.addWidget(self._auto_name)
        layout.addWidget(naming_box)

        hotkeys_box = QGroupBox("Hotkeys")
        hotkeys_layout = QVBoxLayout(hotkeys_box)
        hotkeys_layout.setSpacing(6)
        self._add_checkbox(hotkeys_layout, "global_hotkeys_enabled",
                           "Enable global hotkeys (work while the app is in the background)")
        for field, label in _MAIN_HOTKEYS:
            self._add_hotkey_row(hotkeys_layout, field, label)
        layout.addWidget(hotkeys_box)

        layout.addWidget(self._build_overlay_box())

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

        # Buttons sit outside the scroll area so they're always visible.
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

    def _build_updates_box(self) -> QGroupBox:
        box = QGroupBox("Updates")
        box_layout = QVBoxLayout(box)
        row = QHBoxLayout()
        row.addWidget(QLabel(f"Version {__version__}"))
        self._update_status_lbl = QLabel("")
        self._update_status_lbl.setStyleSheet("color: #888899;")
        row.addWidget(self._update_status_lbl, 1)
        self._check_updates_btn = QPushButton("Check for Updates")
        self._check_updates_btn.setObjectName("ghostBtn")
        self._check_updates_btn.clicked.connect(self._on_check_updates)
        row.addWidget(self._check_updates_btn)
        box_layout.addLayout(row)
        self._add_checkbox(box_layout, "check_updates_on_startup",
                           "Automatically check for updates when opening")
        return box

    def _build_companion_box(self) -> QGroupBox:
        box = QGroupBox("Companion app")
        box_layout = QVBoxLayout(box)
        self._companion_enabled = QCheckBox("Allow the phone companion app to connect over Wi-Fi")
        self._companion_enabled.setChecked(self._cfg.companion_enabled)
        self._companion_enabled.toggled.connect(self._on_companion_toggled)
        box_layout.addWidget(self._companion_enabled)

        get_app_btn = QPushButton("Get the companion app ↗")
        get_app_btn.setObjectName("ghostBtn")
        get_app_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/JacksonW98/fromsave-companion/releases/latest")
        ))
        self._companion_reveal_btn = QPushButton("Show connection info")
        self._companion_reveal_btn.setObjectName("ghostBtn")
        self._companion_reveal_btn.clicked.connect(self._on_companion_reveal)
        for btn in (get_app_btn, self._companion_reveal_btn):
            row = QHBoxLayout()
            row.addWidget(btn)
            row.addStretch()
            box_layout.addLayout(row)

        self._companion_info = QLabel("")
        self._companion_info.setStyleSheet("color: #888899;")
        self._companion_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box_layout.addWidget(self._companion_info)

        hint = QLabel(
            "The address and code shown are private to your home network — "
            "they are not visible to the internet and reveal nothing about you."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666677; font-size: 11px;")
        box_layout.addWidget(hint)
        self._refresh_companion_info()
        return box

    def _build_overlay_box(self) -> QGroupBox:
        box = QGroupBox("Overlay")
        box_layout = QVBoxLayout(box)
        box_layout.setSpacing(6)

        opacity_row = self._labelled_row(box_layout, "Opacity")
        self._overlay_opacity_slider = _NoScrollSlider(Qt.Horizontal)
        self._overlay_opacity_slider.setRange(20, 100)
        self._overlay_opacity_slider.setValue(round(self._cfg.overlay_opacity * 100))
        opacity_row.addWidget(self._overlay_opacity_slider, 1)
        value_lbl = QLabel(f"{self._overlay_opacity_slider.value()}%")
        value_lbl.setFixedWidth(40)
        self._overlay_opacity_slider.valueChanged.connect(lambda v: value_lbl.setText(f"{v}%"))
        opacity_row.addWidget(value_lbl)

        self._add_hotkey_row(box_layout, "hotkey_toggle_overlay", "Toggle overlay")
        hint = QLabel("Overlay hotkeys  (active only while the overlay is shown)")
        hint.setStyleSheet("color: #888899; font-size: 11px;")
        box_layout.addWidget(hint)
        for field, label in _OVERLAY_HOTKEYS:
            self._add_hotkey_row(box_layout, field, label)
        return box

    def _add_checkbox(self, layout: QVBoxLayout, field: str, text: str) -> QCheckBox:
        checkbox = QCheckBox(text)
        checkbox.setChecked(getattr(self._cfg, field))
        layout.addWidget(checkbox)
        self._checkboxes[field] = checkbox
        return checkbox

    @staticmethod
    def _labelled_row(parent_layout: QVBoxLayout, label: str) -> QHBoxLayout:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        lbl = QLabel(label)
        lbl.setFixedWidth(130)
        row_layout.addWidget(lbl)
        parent_layout.addWidget(row)
        return row_layout

    def _add_hotkey_row(self, parent_layout: QVBoxLayout, field: str, label: str) -> None:
        row = self._labelled_row(parent_layout, label)
        editor = QKeySequenceEdit(QKeySequence(getattr(self._cfg, field)))
        editor.setMaximumWidth(160)
        row.addWidget(editor)
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(72)
        clear_btn.setObjectName("ghostBtn")
        clear_btn.clicked.connect(editor.clear)
        row.addWidget(clear_btn)
        row.addStretch()
        self._hotkey_edits[field] = editor

    def _add_game_row(self, name: str, mode: str, path_text: str) -> None:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(8)

        lbl = QLabel(name)
        lbl.setFixedWidth(130)
        mode_combo = _NoScrollComboBox()
        mode_combo.setFixedWidth(110)
        mode_combo.addItem("File", "file")
        mode_combo.addItem("Multiple files", "files")
        mode_combo.addItem("Folder", "folder")
        mode_combo.setCurrentIndex(max(0, mode_combo.findData(mode)))
        edit = QLineEdit(path_text)
        browse_btn = QPushButton()
        set_path_input_mode(edit, browse_btn, mode)
        reveal_btn = QPushButton("Click to reveal")
        reveal_btn.setObjectName("revealPathBtn")
        reveal_btn.setVisible(False)
        del_btn = QPushButton("×")
        del_btn.setObjectName("dangerBtn")
        del_btn.setFixedWidth(40)

        row = _GameRow(name, mode, widget, mode_combo, edit, browse_btn, reveal_btn)
        browse_btn.clicked.connect(lambda: browse_save_path(self, edit, row.mode))
        reveal_btn.clicked.connect(lambda: self._reveal_path(row))
        del_btn.clicked.connect(lambda: self._remove_game_row(row))
        mode_combo.currentIndexChanged.connect(lambda: self._on_row_mode_changed(row))

        row_layout.addWidget(lbl)
        row_layout.addWidget(mode_combo)
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(reveal_btn, 1)
        row_layout.addWidget(browse_btn)
        row_layout.addWidget(del_btn)
        self._game_rows.append(row)
        self._paths_layout.addWidget(widget)

    def _on_row_mode_changed(self, row: _GameRow) -> None:
        new_mode = row.mode_combo.currentData()
        if new_mode != row.mode:
            row.mode = new_mode
            row.edit.clear()
            set_path_input_mode(row.edit, row.browse_btn, new_mode)

    def _apply_path_hide(self) -> None:
        hide = self._checkboxes["hide_paths"].isChecked()
        for row in self._game_rows:
            row.edit.setVisible(not hide)
            row.reveal_btn.setVisible(hide)

    @staticmethod
    def _reveal_path(row: _GameRow) -> None:
        row.reveal_btn.setVisible(False)
        row.edit.setVisible(True)

    def _remove_game_row(self, row: _GameRow) -> None:
        reply = QMessageBox.question(
            self, "Remove game",
            f"Remove '{row.name}' from the list?\n\nThis will not delete any saved slots.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        row.widget.hide()
        row.widget.deleteLater()
        self._game_rows.remove(row)
        self._removed_game_names.append(row.name)

    def _on_add_game(self) -> None:
        dlg = AddGameDialog(self)
        if not dlg.exec():
            return
        name, mode, path_text = dlg.result
        if any(row.name == name for row in self._game_rows):
            QMessageBox.warning(self, "Duplicate", f"'{name}' is already in the list.")
            return
        self._add_game_row(name, mode, path_text)

    def _on_companion_toggled(self, checked: bool) -> None:
        if checked and not self._cfg.companion_firewall_notice_shown:
            QMessageBox.information(
                self, "Companion app",
                "Windows may show a popup asking to allow FromSave network access.\n\n"
                "Make sure you click Allow — if you click Cancel or Deny, the phone "
                "app won't be able to connect, and you'll need to fix it manually in "
                "Windows Firewall settings."
            )
            self._cfg.companion_firewall_notice_shown = True
            if self._on_companion_notice_shown is not None:
                self._on_companion_notice_shown()
        self._cfg.companion_enabled = checked
        if self._on_companion_toggle is not None:
            if token := self._on_companion_toggle(checked):
                self._cfg.companion_token = token
        if not checked:
            self._companion_info_visible = False
        self._refresh_companion_info()

    def _on_companion_reveal(self) -> None:
        self._companion_info_visible = not self._companion_info_visible
        self._refresh_companion_info()

    def _refresh_companion_info(self) -> None:
        enabled = self._companion_enabled.isChecked()
        show = enabled and self._companion_info_visible
        self._companion_reveal_btn.setEnabled(enabled)
        self._companion_reveal_btn.setText("Hide connection info" if show else "Show connection info")
        self._companion_info.setVisible(show)
        if not enabled:
            return
        if not self._cfg.companion_token:
            self._cfg.companion_token = api_server.generate_pair_code()
        self._companion_info.setText(
            f"In the phone app, connect to  {api_server.local_ip()}:{self._cfg.companion_port}"
            f"  with pairing code  {self._cfg.companion_token}"
        )

    def _form_values(self) -> dict:
        """Config field values currently shown by the form (except the companion toggle)."""
        values = {field: cb.isChecked() for field, cb in self._checkboxes.items()}
        values.update({field: e.keySequence().toString() for field, e in self._hotkey_edits.items()})
        values["auto_name_imports"] = self._auto_name.isChecked()
        values["overlay_opacity"] = self._overlay_opacity_slider.value() / 100.0
        return values

    def _has_changes(self) -> bool:
        return self._form_values() != self._initial_values or self.result_games != self._initial_games

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
        for field, value in self._form_values().items():
            setattr(self._cfg, field, value)
        self._cfg.companion_enabled = self._companion_enabled.isChecked()
        self.accept()

    def _on_check_updates(self) -> None:
        self._check_updates_btn.setEnabled(False)
        self._update_flow.start()

    @property
    def result_config(self) -> config.Config:
        return self._cfg

    @property
    def result_games(self) -> list[storage.GameConfig]:
        return [row.to_config() for row in self._game_rows]

    @property
    def removed_game_names(self) -> list[str]:
        return self._removed_game_names
