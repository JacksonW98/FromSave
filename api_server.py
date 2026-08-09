"""Local HTTP API so the FromSave companion phone app can browse and load saves.

The server binds on the LAN and requires the pairing code from Settings in an
X-Api-Token header on every request. It runs on a daemon thread; any action
that changes saves emits saves_changed so the main window can refresh.
"""
from __future__ import annotations

import json
import logging
import secrets
import socket
import string
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from PySide6.QtCore import QObject, Signal

import storage
from version import __version__

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8765
DISCOVERY_PORT = 8766
_DISCOVERY_PROBE = b"FROMSAVE_DISCOVERY_V1"


def generate_pair_code() -> str:
    """Six characters from an alphabet without lookalikes (no 0/O, 1/I)."""
    alphabet = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1")
    return "".join(secrets.choice(alphabet) for _ in range(6))


def local_ip() -> str:
    """Best-effort LAN address of this machine, for display in Settings."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class _ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _find_game(name: str) -> storage.GameConfig:
    game = next((g for g in storage.load_games() if g.name == name), None)
    if game is None:
        raise _ApiError(404, f"Unknown game: {name}")
    return game


def _find_slot(game: str, profile: str, slot_name: str) -> storage.SaveSlot:
    slot = next((s for s in storage.load_slots(game, profile) if s.name == slot_name), None)
    if slot is None:
        raise _ApiError(404, f"Unknown slot: {slot_name}")
    return slot


def _slot_json(slot: storage.SaveSlot) -> dict:
    return {
        "name": slot.name,
        "created": slot.date_created.isoformat() if slot.date_created else None,
        "modified": slot.date_modified.isoformat() if slot.date_modified else None,
        "notes": slot.notes,
    }


class _Handler(BaseHTTPRequestHandler):
    server_version = "FromSaveCompanion/" + __version__
    # Set by CompanionServer.start() on the class the server is built with.
    token = ""
    on_saves_changed = staticmethod(lambda: None)

    # -- plumbing ---------------------------------------------------------

    def log_message(self, fmt, *args):  # route http.server chatter to our logger
        logger.debug("companion http: " + fmt, *args)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        supplied = self.headers.get("X-Api-Token", "")
        if self.token and secrets.compare_digest(supplied, self.token):
            return True
        self._send_json({"error": "Invalid pairing code"}, 401)
        return False

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise _ApiError(400, "Invalid JSON body")

    def _query(self) -> dict:
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(self.path)
        return {k: v[0] for k, v in parse_qs(parsed.query).items()}

    def _route(self, method: str) -> None:
        from urllib.parse import urlparse
        path = urlparse(self.path).path.rstrip("/")
        if not self._check_auth():
            return
        try:
            payload = self._dispatch(method, path)
        except _ApiError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except Exception as exc:  # storage/filesystem errors -> readable message
            logger.exception("Companion API error handling %s %s", method, path)
            self._send_json({"error": str(exc)}, 500)
        else:
            self._send_json(payload)

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

    # -- endpoints --------------------------------------------------------

    def _dispatch(self, method: str, path: str) -> dict:
        if method == "GET" and path == "/api/ping":
            return {"app": "FromSave Manager", "version": __version__}

        if method == "GET" and path == "/api/games":
            return {"games": [{"name": g.name, "save_mode": g.save_mode}
                              for g in storage.load_games()]}

        if method == "GET" and path == "/api/profiles":
            q = self._query()
            game = q.get("game") or ""
            _find_game(game)
            return {"profiles": storage.load_profiles(game)}

        if method == "GET" and path == "/api/slots":
            q = self._query()
            game, profile = q.get("game") or "", q.get("profile") or ""
            _find_game(game)
            return {"slots": [_slot_json(s) for s in storage.load_slots(game, profile)]}

        if method == "POST" and path == "/api/load":
            body = self._read_body()
            game_cfg = _find_game(body.get("game") or "")
            slot = _find_slot(game_cfg.name, body.get("profile") or "", body.get("slot") or "")
            storage.load_save(slot, game_cfg)
            logger.info("Companion app loaded slot %r (%s / %s)",
                        slot.name, game_cfg.name, slot.profile)
            self.on_saves_changed()
            return {"loaded": slot.name}

        if method == "POST" and path == "/api/import":
            body = self._read_body()
            game_cfg = _find_game(body.get("game") or "")
            profile = body.get("profile") or ""
            name = (body.get("name") or "").strip() or storage.auto_slot_name(game_cfg.name, profile)
            slot = storage.import_save(game_cfg.name, profile, name, game_cfg)
            logger.info("Companion app imported slot %r (%s / %s)",
                        slot.name, game_cfg.name, profile)
            self.on_saves_changed()
            return {"imported": _slot_json(slot)}

        raise _ApiError(404, f"No such endpoint: {method} {path}")


class CompanionServer(QObject):
    """Owns the HTTP server thread and bridges remote actions into Qt signals."""

    saves_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._udp: Optional[socket.socket] = None

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self, port: int, token: str) -> bool:
        self.stop()
        if not token:
            logger.warning("Companion server not started: no pairing code configured")
            return False

        handler = type("BoundHandler", (_Handler,), {
            "token": token,
            "on_saves_changed": staticmethod(self.saves_changed.emit),
        })
        try:
            self._httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
        except OSError as exc:
            logger.warning("Companion server failed to bind port %d: %s", port, exc)
            self._httpd = None
            return False

        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self._start_discovery(port)
        logger.info("Companion server listening on %s:%d", local_ip(), port)
        return True

    def _start_discovery(self, http_port: int) -> None:
        """Answer UDP broadcast probes so the phone app can find this PC
        without the user typing an IP address."""
        try:
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp.bind(("", DISCOVERY_PORT))
        except OSError as exc:
            logger.warning("Discovery listener failed to bind port %d: %s",
                           DISCOVERY_PORT, exc)
            return
        self._udp = udp
        threading.Thread(
            target=self._discovery_loop, args=(udp, http_port), daemon=True
        ).start()

    def _discovery_loop(self, udp: socket.socket, http_port: int) -> None:
        reply = json.dumps({
            "app": "FromSave Manager",
            "version": __version__,
            "host": socket.gethostname(),
            "port": http_port,
        }).encode("utf-8")
        while True:
            try:
                data, addr = udp.recvfrom(1024)
            except OSError:
                return  # socket closed by stop()
            if data.strip() != _DISCOVERY_PROBE:
                continue
            try:
                udp.sendto(reply, addr)
            except OSError:
                logger.debug("Failed to answer discovery probe from %s", addr)

    def stop(self) -> None:
        if self._udp is not None:
            udp = self._udp
            self._udp = None
            try:
                udp.close()
            except OSError:
                pass
        if self._httpd is not None:
            httpd = self._httpd
            self._httpd = None
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:
                logger.exception("Failed to stop companion server cleanly")
            self._thread = None
