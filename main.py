import ctypes
import os
import sys
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
import app_logging
import app_paths
import config as config_module
from ui.main_window import MainWindow

_CA_BUNDLE_PATHS = (
    "/etc/ssl/certs/ca-certificates.crt",  # Debian/Ubuntu/Arch/SteamOS
    "/etc/pki/tls/certs/ca-bundle.crt",    # Fedora/RHEL
    "/etc/ssl/ca-bundle.pem",              # openSUSE
    "/etc/ssl/cert.pem",                   # misc
)


def _configure_ssl_certs() -> None:
    """Point the bundled OpenSSL at the host's CA store; it only knows the
    build distro's cert paths, which may not exist on the host."""
    if not (getattr(sys, "frozen", False) and sys.platform.startswith("linux")):
        return
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return
    for path in _CA_BUNDLE_PATHS:
        if os.path.exists(path):
            os.environ["SSL_CERT_FILE"] = path
            break


def _fix_helper_permissions() -> None:
    """Restore exec bits lost when an older updater extracted a release zip."""
    if not (getattr(sys, "frozen", False) and sys.platform.startswith("linux")):
        return
    helper = app_paths.bundled_dir() / "PySide6" / "Qt" / "libexec" / "QtWebEngineProcess"
    if helper.exists() and not os.access(helper, os.X_OK):
        os.chmod(helper, 0o755)


def main() -> None:
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FromSave.Manager")
    _configure_ssl_certs()
    _fix_helper_permissions()

    log_file = app_logging.configure_logging()
    app_logging.install_exception_hooks()

    is_first_run = not config_module._CONFIG_FILE.exists()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("FromSave Manager")
    app.setWindowIcon(QIcon(str(app_paths.bundled_dir() / "fromsave.ico")))

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
