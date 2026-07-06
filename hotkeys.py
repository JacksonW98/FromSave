import ctypes
import ctypes.util
import logging
import sys

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

try:
    from pynput import keyboard as _kb
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    logger.info("pynput is not installed; global hotkeys unavailable")
#TODO test on windows


def _is_trusted() -> bool:
    """Return True if this process has macOS Accessibility permission (or is not on macOS)."""
    if sys.platform != "darwin":
        return True
    try:
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        logger.exception("Failed to check macOS Accessibility trust status")
        return False

# Qt's portable QKeySequence names for special keys that don't match pynput's
# Key enum names when merely lowercased (e.g. "Return" -> "enter", not "return").
_SPECIAL_KEY_MAP = {
    "ins": "insert",
    "del": "delete",
    "return": "enter",
    "enter": "enter",
    "esc": "esc",
    "backspace": "backspace",
    "tab": "tab",
    "home": "home",
    "end": "end",
    "pgup": "page_up",
    "pgdown": "page_down",
    "capslock": "caps_lock",
    "numlock": "num_lock",
    "scrolllock": "scroll_lock",
    "print": "print_screen",
    "pause": "pause",
    "menu": "menu",
    "space": "space",
}


def _qt_to_pynput(qt_seq: str) -> str | None:
    """Convert a Qt portable key sequence string (e.g. 'Ctrl+S', 'F5') to pynput GlobalHotKeys format."""
    if not qt_seq:
        return None

    parts = [p.strip() for p in qt_seq.split("+")]
    out = []
    for p in parts:
        if p == "Ctrl":
            # Qt maps Cmd->Ctrl on macOS in its portable format
            out.append("<cmd>" if sys.platform == "darwin" else "<ctrl>")
        elif p == "Meta":
            # Qt's Meta = physical Ctrl on macOS, Win key elsewhere
            out.append("<ctrl>" if sys.platform == "darwin" else "<cmd>")
        elif p == "Alt":
            out.append("<alt>")
        elif p == "Shift":
            out.append("<shift>")
        elif len(p) >= 2 and p[0] == "F" and p[1:].isdigit():
            out.append(f"<{p.lower()}>")
        elif p.lower() in _SPECIAL_KEY_MAP:
            out.append(f"<{_SPECIAL_KEY_MAP[p.lower()]}>")
        elif len(p) == 1:
            out.append(p.lower())
        else:
            out.append(f"<{p.lower()}>")

    return "+".join(out)


class GlobalHotkeyListener(QObject):
    """Listens for system-wide hotkeys and emits Qt signals (safe to connect to GUI slots)."""

    import_triggered = Signal()
    load_triggered = Signal()
    replace_triggered = Signal()
    ro_toggle_triggered = Signal()
    next_slot_triggered = Signal()
    prev_slot_triggered = Signal()
    toggle_overlay_triggered = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._listener = None

    def start(
        self,
        hotkey_import: str,
        hotkey_load: str,
        hotkey_replace: str,
        hotkey_ro: str,
        hotkey_next_slot: str = "",
        hotkey_prev_slot: str = "",
        hotkey_toggle_overlay: str = "",
        enabled: bool = True,
    ) -> bool:
        """Start the listener. Returns True if started, False if unavailable, not trusted, or disabled."""
        self.stop()
        if not enabled:
            logger.info("Global hotkeys disabled in settings")
            return False
        if not _AVAILABLE:
            logger.warning("Global hotkeys unavailable because pynput could not be imported")
            return False
        if not _is_trusted():
            logger.warning("Global hotkeys unavailable because the process is not trusted")
            return False

        bindings: dict[str, object] = {}
        if pk := _qt_to_pynput(hotkey_import):
            bindings[pk] = self.import_triggered.emit
        if pk := _qt_to_pynput(hotkey_load):
            bindings[pk] = self.load_triggered.emit
        if pk := _qt_to_pynput(hotkey_replace):
            bindings[pk] = self.replace_triggered.emit
        if pk := _qt_to_pynput(hotkey_ro):
            bindings[pk] = self.ro_toggle_triggered.emit
        if pk := _qt_to_pynput(hotkey_next_slot):
            bindings[pk] = self.next_slot_triggered.emit
        if pk := _qt_to_pynput(hotkey_prev_slot):
            bindings[pk] = self.prev_slot_triggered.emit
        if pk := _qt_to_pynput(hotkey_toggle_overlay):
            bindings[pk] = self.toggle_overlay_triggered.emit

        if not bindings:
            logger.info("No global hotkeys configured")
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
                pass
            self._listener = None
