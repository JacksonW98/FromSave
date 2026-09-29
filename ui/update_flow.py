import logging
import sys

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QWidget

import updater
from version import __version__

logger = logging.getLogger(__name__)


class UpdateFlow(QObject):
    """Check for an update, ask to install it, download with progress, then restart.

    With quiet=True, check failures and "up to date" results aren't shown to the user.
    """

    status_changed = Signal(str)
    finished = Signal()  # emitted when the flow ends without restarting the app

    def __init__(self, parent: QWidget, quiet: bool = False) -> None:
        super().__init__(parent)
        self._parent = parent
        self._quiet = quiet
        self._progress: QProgressDialog | None = None
        self._checker = updater.UpdateChecker()
        self._checker.check_succeeded.connect(self._on_check_succeeded)
        self._checker.check_failed.connect(self._on_check_failed)
        self._checker.download_progress.connect(self._on_download_progress)
        self._checker.download_ready.connect(self._on_download_ready)
        self._checker.download_failed.connect(self._on_download_failed)

    def start(self) -> None:
        self.status_changed.emit("Checking for updates…")
        self._checker.start_check()

    def _on_check_failed(self, message: str) -> None:
        self.status_changed.emit("Update check failed.")
        if self._quiet:
            logger.warning("Update check failed: %s", message)
        else:
            QMessageBox.warning(self._parent, "Update check failed",
                                f"Couldn't check for updates:\n\n{message}")
        self.finished.emit()

    def _on_check_succeeded(self, info) -> None:
        if info is None:
            self.status_changed.emit(f"You're up to date  (v{__version__}).")
            self.finished.emit()
            return
        self.status_changed.emit(f"Version {info.version} is available.")
        reply = QMessageBox.question(
            self._parent, "Update available",
            f"Version {info.version} is available (you have v{__version__}).\n\n"
            f"{info.notes}\n\nDownload and install it now? "
            "The app will close and restart automatically.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            self.finished.emit()
            return
        self._progress = QProgressDialog("Downloading update…", "", 0, 100, self._parent)
        self._progress.setCancelButton(None)
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.show()
        self._checker.start_download(info)

    def _on_download_progress(self, downloaded: int, total: int) -> None:
        if self._progress is None:
            return
        if total > 0:
            self._progress.setValue(int(downloaded * 100 / total))
        else:
            self._progress.setLabelText(f"Downloading update… {downloaded // (1024 * 1024)} MB")

    def _close_progress(self) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress = None

    def _on_download_failed(self, message: str) -> None:
        self._close_progress()
        self.status_changed.emit("Update download failed.")
        QMessageBox.warning(self._parent, "Update failed",
                            f"Couldn't download the update:\n\n{message}")
        self.finished.emit()

    def _on_download_ready(self, staged_dir, zip_path) -> None:
        self._close_progress()
        if not getattr(sys, "frozen", False):
            QMessageBox.information(
                self._parent, "Update downloaded",
                "The update was downloaded, but self-install only works in the packaged "
                "build. Since this is running from source, please pull the latest "
                "changes instead.",
            )
            self.finished.emit()
            return
        updater.apply_update_and_restart(staged_dir, zip_path)
        QApplication.instance().quit()
