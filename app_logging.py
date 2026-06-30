"""Application logging setup for FromSave Manager."""
from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

_ROOT = Path(__file__).parent
LOG_DIR = _ROOT / "logs"
LOG_FILE = LOG_DIR / "fromsave.log"


def configure_logging() -> Path:
    """Configure file logging and return the active log path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    if any(getattr(h, "_fromsave_handler", False) for h in root.handlers):
        return LOG_FILE

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d %(message)s"
    )

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler._fromsave_handler = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    logging.getLogger(__name__).info("Logging started: %s", LOG_FILE)
    return LOG_FILE


def install_exception_hooks() -> None:
    """Log uncaught Python and Qt exceptions before the app exits."""

    def handle_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger(__name__).critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = handle_exception

    def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        logging.getLogger(__name__).critical(
            "Uncaught thread exception",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = handle_thread_exception

    try:
        from PySide6.QtCore import qInstallMessageHandler
    except ImportError:
        return

    def qt_message_handler(mode, context, message: str) -> None:
        logger = logging.getLogger("qt")
        source = f"{context.file}:{context.line}" if context and context.file else ""
        text = f"{source} {message}".strip()
        mode_name = getattr(mode, "name", str(mode)).lower()
        if "fatal" in mode_name:
            logger.critical(text)
        elif "critical" in mode_name:
            logger.error(text)
        elif "warning" in mode_name:
            logger.warning(text)
        elif "debug" in mode_name:
            logger.debug(text)
        else:
            logger.info(text)

    qInstallMessageHandler(qt_message_handler)
