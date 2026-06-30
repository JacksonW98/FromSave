import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
import app_logging
import config as config_module
from ui.main_window import MainWindow


def main() -> None:
    log_file = app_logging.configure_logging()
    app_logging.install_exception_hooks()

    is_first_run = not config_module._CONFIG_FILE.exists()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("FromSave Manager")

    font = app.font()
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.status_bar.showMessage("Logging started.", 5000)
    window.show()

    if is_first_run:
        QTimer.singleShot(0, window.show_first_run_dialog)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
