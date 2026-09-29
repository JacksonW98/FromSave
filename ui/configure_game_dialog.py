from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.save_path_widgets import SaveModeGroup


class ConfigureGameDialog(QDialog):
    """Ask for the save mode of a game folder that has no game.json yet."""

    def __init__(self, game_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Set up {game_name}")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(16, 16, 16, 16)

        intro = QLabel(
            f"A saves folder for <b>{game_name}</b> was found but it hasn't been "
            "configured yet. Select the save type below, then set the save path in "
            "<b>Settings</b>."
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.RichText)
        layout.addWidget(intro)

        self._mode_group = SaveModeGroup()
        layout.addWidget(self._mode_group)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        skip_btn = QPushButton("Skip for now")
        skip_btn.clicked.connect(self.reject)
        configure_btn = QPushButton("Configure")
        configure_btn.setObjectName("primaryBtn")
        configure_btn.clicked.connect(self.accept)
        btn_row.addWidget(skip_btn)
        btn_row.addWidget(configure_btn)
        layout.addLayout(btn_row)

    @property
    def result_mode(self) -> str:
        return self._mode_group.mode()
