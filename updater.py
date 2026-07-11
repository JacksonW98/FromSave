"""Check GitHub for newer releases of FromSave and self-update the install."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

import app_paths
from version import __version__

logger = logging.getLogger(__name__)

REPO = "JacksonW98/fromsave"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAME_WINDOWS = "FromSave.zip"
ASSET_NAME_LINUX = "FromSave-linux.zip"
_USER_AGENT = "FromSave-Manager-Updater"


def _asset_name() -> str:
    return ASSET_NAME_LINUX if sys.platform.startswith("linux") else ASSET_NAME_WINDOWS


def _expected_binary_name() -> str:
    return "FromSave.exe" if sys.platform == "win32" else "FromSave"


class UpdateInfo:
    def __init__(self, version: str, download_url: str, size: int, notes: str):
        self.version = version
        self.download_url = download_url
        self.size = size
        self.notes = notes


def _version_tuple(v: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", v)
    return tuple(int(p) for p in parts) or (0,)


def is_newer(remote_version: str, local_version: str = __version__) -> bool:
    return _version_tuple(remote_version) > _version_tuple(local_version)


def check_latest_release(timeout: float = 10.0) -> Optional[UpdateInfo]:
    """Return update info if GitHub has a newer release than this build, else None."""
    req = urllib.request.Request(
        API_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": _USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)

    tag = data.get("tag_name", "")
    if not tag or not is_newer(tag):
        return None

    asset_name = _asset_name()
    asset = next((a for a in data.get("assets", []) if a.get("name") == asset_name), None)
    if asset is None:
        logger.warning("Release %s has no %s asset", tag, asset_name)
        return None

    return UpdateInfo(
        version=tag,
        download_url=asset["browser_download_url"],
        size=asset.get("size", 0),
        notes=(data.get("body") or "").strip(),
    )


def download_update(info: UpdateInfo, on_progress=None) -> Path:
    """Download the release zip to a temp file and return its path."""
    fd, tmp_name = tempfile.mkstemp(prefix="fromsave_update_", suffix=".zip")
    os.close(fd)
    tmp_path = Path(tmp_name)

    req = urllib.request.Request(info.download_url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp, open(tmp_path, "wb") as f:
        total = info.size or int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if on_progress:
                on_progress(downloaded, total)
    return tmp_path


def extract_update(zip_path: Path) -> Path:
    """Extract the downloaded zip and return the folder containing the FromSave binary."""
    staging_dir = Path(tempfile.mkdtemp(prefix="fromsave_update_extract_"))
    binary_name = _expected_binary_name()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            extracted = zf.extract(info, staging_dir)
            if info.is_dir():
                continue
            # zipfile drops Unix permissions on extract; restore them from
            # the zip entry, or force exec on known binaries as a fallback.
            mode = (info.external_attr >> 16) & 0o7777
            if mode:
                os.chmod(extracted, mode)
            elif info.filename.endswith(binary_name) or "libexec/" in info.filename:
                os.chmod(extracted, 0o755)
    if (staging_dir / binary_name).exists():
        return staging_dir
    for child in staging_dir.iterdir():
        if child.is_dir() and (child / binary_name).exists():
            return child
    raise FileNotFoundError(f"{binary_name} not found in downloaded release")


def apply_update_and_restart(staged_dir: Path, zip_path: Optional[Path] = None) -> None:
    """Hand off to a detached helper script that waits for this process to exit,
    copies the staged build over the current install, relaunches the app, and
    cleans up temp files. The caller must quit the application right after this."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Self-update is only supported in a packaged build")

    app_dir = app_paths.app_dir()
    exe_name = Path(sys.executable).name
    # staged_dir is either the mkdtemp staging root or one level inside it;
    # never clean up anything above the staging root (its parent is /tmp).
    staging_root = (
        staged_dir
        if staged_dir.name.startswith("fromsave_update_extract_")
        else staged_dir.parent
    )
    cleanup_paths = [str(staging_root)]
    if zip_path is not None:
        cleanup_paths.append(str(zip_path))
    for p in cleanup_paths:
        if "fromsave_update" not in Path(p).name:
            raise RuntimeError(f"Refusing to delete unexpected path: {p}")

    if sys.platform == "win32":
        bat_path = Path(tempfile.gettempdir()) / f"fromsave_update_{os.getpid()}.bat"
        cleanup_cmds = "\n".join(f'del /q "{p}" >nul 2>&1\nrmdir /s /q "{p}" >nul 2>&1' for p in cleanup_paths)
        bat_contents = f"""@echo off
timeout /t 3 /nobreak >nul
robocopy "{staged_dir}" "{app_dir}" /E /R:5 /W:2 >nul
start "" "{app_dir / exe_name}"
{cleanup_cmds}
del "%~f0"
"""
        bat_path.write_text(bat_contents)

        subprocess.Popen(
            ["cmd", "/c", str(bat_path)],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
            cwd=str(app_dir),
        )
    else:
        sh_path = Path(tempfile.gettempdir()) / f"fromsave_update_{os.getpid()}.sh"
        cleanup_cmds = "\n".join(f'rm -rf "{p}"' for p in cleanup_paths)
        sh_contents = f"""#!/bin/sh
sleep 3
cp -a "{staged_dir}/." "{app_dir}/"
chmod +x "{app_dir / exe_name}"
"{app_dir / exe_name}" >/dev/null 2>&1 &
{cleanup_cmds}
rm -f "$0"
"""
        sh_path.write_text(sh_contents)
        os.chmod(sh_path, 0o755)

        subprocess.Popen(
            ["/bin/sh", str(sh_path)],
            start_new_session=True,
            close_fds=True,
            cwd=str(app_dir),
        )


class UpdateChecker(QObject):
    """Runs the check/download/extract steps on a background thread and
    reports back to the Qt main thread via signals."""

    check_succeeded = Signal(object)   # UpdateInfo | None
    check_failed = Signal(str)
    download_progress = Signal(int, int)
    download_ready = Signal(object, object)  # staged_dir: Path, zip_path: Path
    download_failed = Signal(str)

    def start_check(self) -> None:
        threading.Thread(target=self._run_check, daemon=True).start()

    def _run_check(self) -> None:
        try:
            info = check_latest_release()
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            logger.warning("Update check failed: %s", exc)
            self.check_failed.emit(str(exc))
            return
        self.check_succeeded.emit(info)

    def start_download(self, info: UpdateInfo) -> None:
        threading.Thread(target=self._run_download, args=(info,), daemon=True).start()

    def _run_download(self, info: UpdateInfo) -> None:
        try:
            zip_path = download_update(info, on_progress=lambda d, t: self.download_progress.emit(d, t))
            staged_dir = extract_update(zip_path)
        except (urllib.error.URLError, TimeoutError, OSError, zipfile.BadZipFile, FileNotFoundError) as exc:
            logger.warning("Update download failed: %s", exc)
            self.download_failed.emit(str(exc))
            return
        self.download_ready.emit(staged_dir, zip_path)
