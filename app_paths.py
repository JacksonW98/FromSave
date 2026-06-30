"""Shared filesystem locations for FromSave Manager."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def app_dir() -> Path:
    """Return the user-visible application folder.

    In a PyInstaller build, Python modules live under the bundled internal
    folder, but user files should sit beside the executable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_dir() -> Path:
    """Return the folder containing bundled source resources."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)).resolve()


def migrate_from_bundle(*names: str) -> None:
    """Copy existing bundled user files out beside the executable if needed."""
    if not getattr(sys, "frozen", False):
        return

    source_root = bundled_dir()
    target_root = app_dir()
    if source_root == target_root:
        return

    for name in names:
        source = source_root / name
        target = target_root / name
        if not source.exists() or target.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
