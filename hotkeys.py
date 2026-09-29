import ctypes
import ctypes.util
import logging
import os
import sys
from functools import partial

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

try:
    from pynput import keyboard as _kb
    _AVAILABLE = True
    _SHIFT_KEYS = frozenset({_kb.Key.shift, _kb.Key.shift_l, _kb.Key.shift_r})
except ImportError:
    _AVAILABLE = False
    _SHIFT_KEYS = frozenset()
    logger.info("pynput is not installed; global hotkeys unavailable")
#TODO test on windows


def _is_trusted() -> bool:
    """Whether this process has macOS Accessibility permission (always True elsewhere)."""
    if sys.platform != "darwin":
        return True
    try:
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        logger.exception("Failed to check macOS Accessibility trust status")
        return False


def is_wayland_session() -> bool:
    """pynput's global hotkeys rely on X11 and don't receive events under Wayland."""
    return sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


# Qt key names whose pynput equivalent isn't just the lowercased name.
_SPECIAL_KEY_MAP = {
    "ins": "insert",
    "del": "delete",
    "return": "enter",
    "pgup": "page_up",
    "pgdown": "page_down",
    "capslock": "caps_lock",
    "numlock": "num_lock",
    "scrolllock": "scroll_lock",
    "print": "print_screen",
}


def _qt_to_pynput(qt_seq: str) -> str | None:
    """Convert a Qt portable key sequence (e.g. 'Ctrl+S', 'F5') to pynput's hotkey format."""
    if not qt_seq:
        return None
    mac = sys.platform == "darwin"
    out = []
    for part in (p.strip() for p in qt_seq.split("+")):
        if part == "Ctrl":
            out.append("<cmd>" if mac else "<ctrl>")  # Qt reports Cmd as Ctrl on macOS
        elif part == "Meta":
            out.append("<ctrl>" if mac else "<cmd>")
        elif len(part) == 1:
            out.append(part.lower())
        else:
            name = part.lower()
            out.append(f"<{_SPECIAL_KEY_MAP.get(name, name)}>")
    return "+".join(out)


class GlobalHotkeyListener(QObject):
    """Listens for system-wide hotkeys and emits triggered(action) on the Qt thread."""

    triggered = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._listener = None

    def start(self, hotkeys: dict[str, str]) -> bool:
        """Listen for {action: Qt key sequence}. Returns False if nothing could be started."""
        self.stop()
        if not _AVAILABLE:
            logger.warning("Global hotkeys unavailable because pynput could not be imported")
            return False
        if not _is_trusted():
            logger.warning("Global hotkeys unavailable because the process is not trusted")
            return False

        bindings = {}
        for action, key in hotkeys.items():
            if pk := _qt_to_pynput(key):
                bindings[pk] = partial(self.triggered.emit, action)
        if not bindings:
            return False

        try:
            self._listener = _kb.GlobalHotKeys(bindings)
            self._listener.daemon = True
            self._listener.start()
            logger.info("Global hotkeys started: %s", sorted(bindings))
            return True
        except Exception:
            logger.exception("Failed to start global hotkeys: %s", sorted(bindings))
            self._listener = None
            return False

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                logger.exception("Failed to stop global hotkey listener cleanly")
            self._listener = None


class GlobalTextInputListener(QObject):
    """Capture typed text globally for the overlay's name prompt.

    On Windows the keystrokes are suppressed so the game doesn't also receive them.
    """

    text_changed = Signal(str)
    submitted = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._listener = None
        self._text = ""
        self._replace_on_next_character = False
        self._shift_held = False

    def start(self, initial_text: str) -> bool:
        self.stop()
        if not _AVAILABLE or not _is_trusted():
            return False

        self._text = initial_text
        self._replace_on_next_character = True
        self._shift_held = False
        try:
            self._listener = _kb.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
                suppress=sys.platform == "win32",
            )
            self._listener.daemon = True
            self._listener.start()
            return True
        except Exception:
            logger.exception("Failed to start global text input listener")
            self._listener = None
            return False

    def stop(self) -> None:
        if self._listener is not None:
            listener = self._listener
            self._listener = None
            try:
                listener.stop()
                # The Windows hook is released asynchronously; wait briefly so an
                # immediately following hotkey isn't swallowed by this listener.
                listener.join(0.25)
            except Exception:
                logger.exception("Failed to stop global text input listener cleanly")

    def _on_release(self, key):
        if key in _SHIFT_KEYS:
            self._shift_held = False

    def _on_press(self, key):
        if key in _SHIFT_KEYS:
            self._shift_held = True
            return
        if key == _kb.Key.enter:
            self.submitted.emit(self._text)
            return False
        if key == _kb.Key.esc:
            self.cancelled.emit()
            return False
        if key == _kb.Key.backspace:
            if self._replace_on_next_character:
                self._text = ""
                self._replace_on_next_character = False
            else:
                self._text = self._text[:-1]
            self.text_changed.emit(self._text)
            return

        char = " " if key == _kb.Key.space else getattr(key, "char", None)
        if char and char.isprintable():
            # The suppressed hook doesn't reliably apply Shift, so track it ourselves.
            if self._shift_held and char.isalpha():
                char = char.upper()
            self._text = char if self._replace_on_next_character else self._text + char
            self._replace_on_next_character = False
            self.text_changed.emit(self._text)
