import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import app_logging
from ui.main_window import MainWindow


def main() -> None:
    log_file = app_logging.configure_logging()
    app_logging.install_exception_hooks()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("FromSave Manager")

    font = app.font()
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.status_bar.showMessage(f"Ready. Log: {log_file}", 5000)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
