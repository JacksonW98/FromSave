from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QInputDialog, QMessageBox,
)

import storage


class ProfilesDialog(QDialog):
    def __init__(self, game: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Profiles — {game}")
        self.setMinimumWidth(340)
        self.setMinimumHeight(300)
        self._game = game
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()

        self._new_btn = QPushButton("New")
        self._new_btn.setObjectName("primaryBtn")
        self._new_btn.clicked.connect(self._on_new)

        self._rename_btn = QPushButton("Rename")
        self._rename_btn.setEnabled(False)
        self._rename_btn.clicked.connect(self._on_rename)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setObjectName("dangerBtn")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        btn_row.addWidget(self._new_btn)
        btn_row.addWidget(self._rename_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _reload(self, select: str = "") -> None:
        self._list.clear()
        for name in storage.load_profiles(self._game):
            self._list.addItem(name)
        if select:
            items = self._list.findItems(select, Qt.MatchExactly)
            if items:
                self._list.setCurrentItem(items[0])
                return
        if self._list.count():
            self._list.setCurrentRow(0)

    def _on_selection_changed(self) -> None:
        has = self._list.currentRow() >= 0
        self._rename_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)

    def _on_new(self) -> None:
        name, ok = QInputDialog.getText(self, "New profile", "Profile name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if (storage.SAVES_DIR / self._game / name).exists():
            QMessageBox.warning(self, "Profile exists", f"'{name}' already exists.")
            return
        try:
            storage.create_profile(self._game, name)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        self._reload(select=name)

    def _on_rename(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        old_name = item.text()
        name, ok = QInputDialog.getText(self, "Rename profile", "New name:", text=old_name)
        if not ok or not name.strip() or name.strip() == old_name:
            return
        name = name.strip()
        if (storage.SAVES_DIR / self._game / name).exists():
            QMessageBox.warning(self, "Profile exists", f"'{name}' already exists.")
            return
        try:
            storage.rename_profile(self._game, old_name, name)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        item.setText(name)

    def _on_delete(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        name = item.text()
        slot_count = len(storage.load_slots(self._game, name))
        msg = f"Delete profile '{name}'?"
        if slot_count:
            msg += f"\n\nThis will permanently delete {slot_count} save slot{'s' if slot_count != 1 else ''} inside it."
        msg += "\n\nThis cannot be undone."
        reply = QMessageBox.question(
            self, "Delete profile", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            storage.delete_profile(self._game, name)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        self._reload()
