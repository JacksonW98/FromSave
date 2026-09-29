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
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QObject, Signal

import config as config_module
import storage
from version import __version__

logger = logging.getLogger(__name__)

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


def _check_save_path(game_cfg: storage.GameConfig) -> None:
    """Raise a readable error if the game's save path is unset or missing."""
    if game_cfg.save_mode == "files":
        if not game_cfg.save_paths:
            raise _ApiError(409, f"No save path set for {game_cfg.name}. "
                                  f"Set it in the desktop app's Settings.")
        missing = [p for p in game_cfg.save_paths if not Path(p).exists()]
        if missing:
            raise _ApiError(409, f"Save file not found on the PC: {missing[0]}")
        return
    if not game_cfg.save_path:
        raise _ApiError(409, f"No save path set for {game_cfg.name}. "
                              f"Set it in the desktop app's Settings.")
    if not Path(game_cfg.save_path).exists():
        raise _ApiError(409, f"Save path not found on the PC: {game_cfg.save_path}")


def _find_slot(game: str, profile: str, slot_name: str) -> storage.SaveSlot:
    slot = next((s for s in storage.load_slots(game, profile) if s.name == slot_name), None)
    if slot is None:
        raise _ApiError(404, f"Unknown slot: {slot_name}")
    return slot


def _validate_name(name: str) -> str:
    try:
        return storage.validate_entry_name(name)
    except ValueError as e:
        raise _ApiError(400, str(e))


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
    on_sort_changed = staticmethod(lambda mode, desc: None)

    def log_message(self, fmt, *args):
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
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def _route(self, method: str) -> None:
        path = urlparse(self.path).path.rstrip("/")
        if not self._check_auth():
            return
        try:
            payload = self._dispatch(method, path)
        except _ApiError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except Exception as exc:
            logger.exception("Companion API error handling %s %s", method, path)
            self._send_json({"error": str(exc)}, 500)
        else:
            self._send_json(payload)

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

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
            cfg = config_module.load_config()
            slots = storage.load_sorted_slots(game, profile, cfg.slot_sort, cfg.slot_sort_desc)
            return {
                "slots": [_slot_json(s) for s in slots],
                "sort": cfg.slot_sort,
                "desc": cfg.slot_sort_desc,
            }

        if method == "POST" and path == "/api/load":
            body = self._read_body()
            game_cfg = _find_game(body.get("game") or "")
            slot = _find_slot(game_cfg.name, body.get("profile") or "", body.get("slot") or "")
            _check_save_path(game_cfg)
            storage.load_save(slot, game_cfg)
            logger.info("Companion app loaded slot %r (%s / %s)",
                        slot.name, game_cfg.name, slot.profile)
            self.on_saves_changed()
            return {"loaded": slot.name}

        if method == "POST" and path == "/api/import":
            body = self._read_body()
            game_cfg = _find_game(body.get("game") or "")
            profile = body.get("profile") or ""
            _check_save_path(game_cfg)
            raw_name = (body.get("name") or "").strip()
            name = (_validate_name(raw_name) if raw_name
                    else storage.auto_slot_name(game_cfg.name, profile))
            slot = storage.import_save(game_cfg.name, profile, name, game_cfg)
            logger.info("Companion app imported slot %r (%s / %s)",
                        slot.name, game_cfg.name, profile)
            self.on_saves_changed()
            return {"imported": _slot_json(slot)}

        if method == "POST" and path == "/api/sort":
            body = self._read_body()
            mode = body.get("sort")
            if mode not in storage.SORT_MODES:
                raise _ApiError(400, f"Invalid sort mode: {mode}")
            desc = bool(body.get("desc", True))
            cfg = config_module.load_config()
            cfg.slot_sort = mode
            cfg.slot_sort_desc = desc
            config_module.save_config(cfg)
            logger.info("Companion app set slot sort: %s desc=%s", mode, desc)
            self.on_sort_changed(mode, desc)
            return {"sort": mode, "desc": desc}

        if method == "POST" and path == "/api/slot_order":
            body = self._read_body()
            game_cfg = _find_game(body.get("game") or "")
            profile = body.get("profile") or ""
            names = body.get("names")
            if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                raise _ApiError(400, "names must be a list of slot names")
            storage.save_slot_order(game_cfg.name, profile, names)
            logger.info("Companion app reordered slots (%s / %s)", game_cfg.name, profile)
            self.on_saves_changed()
            return {"order": names}

        if method == "POST" and path == "/api/create_profile":
            body = self._read_body()
            game_cfg = _find_game(body.get("game") or "")
            name = _validate_name(body.get("name") or "")
            if (storage.SAVES_DIR / game_cfg.name / name).exists():
                raise _ApiError(409, f"Profile '{name}' already exists.")
            storage.create_profile(game_cfg.name, name)
            logger.info("Companion app created profile %r (%s)", name, game_cfg.name)
            self.on_saves_changed()
            return {"created": name}

        if method == "POST" and path == "/api/rename":
            body = self._read_body()
            game_cfg = _find_game(body.get("game") or "")
            profile = body.get("profile") or ""
            slot = _find_slot(game_cfg.name, profile, body.get("slot") or "")
            new_name = _validate_name(body.get("name") or "")
            if new_name == slot.name:
                return {"renamed": slot.name}
            # Allow case-only renames on case-insensitive filesystems.
            if new_name.lower() != slot.name.lower() and (slot.path.parent / new_name).exists():
                raise _ApiError(409, f"A slot named '{new_name}' already exists.")
            storage.rename_slot(slot, new_name)
            # Keep the renamed slot's position in a custom order.
            order = storage.load_slot_order(game_cfg.name, profile)
            if order:
                storage.save_slot_order(
                    game_cfg.name, profile,
                    [new_name if n == slot.name else n for n in order],
                )
            logger.info("Companion app renamed slot %r -> %r (%s / %s)",
                        slot.name, new_name, game_cfg.name, profile)
            self.on_saves_changed()
            return {"renamed": new_name}

        if method == "POST" and path == "/api/delete":
            body = self._read_body()
            game_cfg = _find_game(body.get("game") or "")
            profile = body.get("profile") or ""
            slot = _find_slot(game_cfg.name, profile, body.get("slot") or "")
            soft = config_module.load_config().soft_delete
            storage.delete_slot(slot, soft=soft)
            logger.info("Companion app deleted slot %r (%s / %s, soft=%s)",
                        slot.name, game_cfg.name, profile, soft)
            self.on_saves_changed()
            return {"deleted": slot.name, "trashed": soft}

        raise _ApiError(404, f"No such endpoint: {method} {path}")


class CompanionServer(QObject):
    """Owns the HTTP server thread and bridges remote actions into Qt signals."""

    saves_changed = Signal()
    sort_changed = Signal(str, bool)

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
            "on_sort_changed": staticmethod(self.sort_changed.emit),
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
                return  # closed by stop()
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
