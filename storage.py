import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent
SAVES_DIR = _ROOT / "saves"
GAMES_FILE = _ROOT / "games.json"

_RESERVED = {"meta.json", "notes.txt"}


@dataclass
class GameConfig:
    name: str
    save_path: str
    save_file: str


@dataclass
class SaveSlot:
    name: str
    game: str
    profile: str
    path: Path
    date_created: Optional[datetime]
    date_modified: Optional[datetime]
    notes: str
    save_file: str


def load_games() -> list[GameConfig]:
    if not GAMES_FILE.exists():
        return []
    with open(GAMES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return [
        GameConfig(name=name, save_path=cfg.get("save_path", ""), save_file=cfg.get("save_file", ""))
        for name, cfg in data.items()
    ]


def load_profiles(game: str) -> list[str]:
    game_dir = SAVES_DIR / game
    if not game_dir.exists():
        return []
    return sorted(p.name for p in game_dir.iterdir() if p.is_dir())


def load_slots(game: str, profile: str) -> list[SaveSlot]:
    profile_dir = SAVES_DIR / game / profile
    if not profile_dir.exists():
        return []
    slots = []
    for slot_dir in sorted(profile_dir.iterdir()):
        if not slot_dir.is_dir():
            continue
        slot = _read_slot(slot_dir, game, profile)
        if slot is not None:
            slots.append(slot)
    return slots


def _read_slot(slot_dir: Path, game: str, profile: str) -> Optional[SaveSlot]:
    # Find the save file first — folder is only a valid slot if one exists.
    save_file = next(
        (f.name for f in slot_dir.iterdir() if f.is_file() and f.name not in _RESERVED),
        None,
    )
    if save_file is None:
        return None

    save_path = slot_dir / save_file
    stat = save_path.stat()

    meta_file = slot_dir / "meta.json"
    notes_file = slot_dir / "notes.txt"

    if not meta_file.exists():
        _create_meta(meta_file, stat)

    if not notes_file.exists():
        notes_file.write_text("", encoding="utf-8")

    date_created, date_modified = _parse_meta(meta_file)

    notes = notes_file.read_text(encoding="utf-8").strip()

    return SaveSlot(
        name=slot_dir.name,
        game=game,
        profile=profile,
        path=slot_dir,
        date_created=date_created,
        date_modified=date_modified,
        notes=notes,
        save_file=save_file,
    )


def _create_meta(meta_file: Path, stat: os.stat_result) -> None:
    created = datetime.fromtimestamp(
        getattr(stat, "st_birthtime", stat.st_ctime)
    )
    modified = datetime.fromtimestamp(stat.st_mtime)
    meta = {
        "created": created.isoformat(timespec="seconds"),
        "modified": modified.isoformat(timespec="seconds"),
    }
    meta_file.write_text(json.dumps(meta, indent=4), encoding="utf-8")


def _parse_meta(meta_file: Path) -> tuple[Optional[datetime], Optional[datetime]]:
    try:
        with open(meta_file, encoding="utf-8") as f:
            meta = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None, None

    date_created = _parse_iso(meta.get("created"))
    date_modified = _parse_iso(meta.get("modified"))
    return date_created, date_modified


def save_notes(slot: SaveSlot, text: str) -> None:
    notes_file = slot.path / "notes.txt"
    notes_file.write_text(text, encoding="utf-8")
    slot.notes = text


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
