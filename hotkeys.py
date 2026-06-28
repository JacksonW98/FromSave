import sys

from PySide6.QtCore import QObject, Signal

try:
    from pynput import keyboard as _kb
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
#TODO test on windows

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
        elif len(p) == 1:
            out.append(p.lower())
        else:
            out.append(f"<{p.lower()}>")

    return "+".join(out)


class GlobalHotkeyListener(QObject):
    """Listens for system-wide hotkeys and emits Qt signals (safe to connect to GUI slots)."""

    import_triggered = Signal()
    load_triggered = Signal()
    ro_toggle_triggered = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._listener = None

    def start(self, hotkey_import: str, hotkey_load: str, hotkey_ro: str) -> None:
        self.stop()
        if not _AVAILABLE:
            return

        bindings: dict[str, object] = {}
        if pk := _qt_to_pynput(hotkey_import):
            bindings[pk] = self.import_triggered.emit
        if pk := _qt_to_pynput(hotkey_load):
            bindings[pk] = self.load_triggered.emit
        if pk := _qt_to_pynput(hotkey_ro):
            bindings[pk] = self.ro_toggle_triggered.emit

        if not bindings:
            return

        try:
            self._listener = _kb.GlobalHotKeys(bindings)
            self._listener.daemon = True
            self._listener.start()
        except Exception:
            self._listener = None

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
