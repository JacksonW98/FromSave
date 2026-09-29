import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import send2trash

from app_paths import app_dir, migrate_from_bundle

migrate_from_bundle("saves")

SAVES_DIR = app_dir() / "saves"
logger = logging.getLogger(__name__)

_RESERVED = {"meta.json", "notes.txt"}
_GAME_CONFIG = "game.json"
_BACKUPS_DIR = "_backups"
_RUN_BACKUPS_DIR = "_run_backups"
_PRACTICE_START_DIR = "_practice_start"
_MAX_BACKUPS = 3

SORT_MODES = ("name", "created", "modified", "custom")

# Games whose saves/ folder ships in the release zip. They're all single-file
# saves, so a fresh install configures them as "file" mode without asking.
BUNDLED_GAMES = {
    "Armored Core VI",
    "Dark Souls II Scholar of the First Sin",
    "Dark Souls III",
    "Dark Souls Remastered",
    "Elden Ring",
    "Sekiro",
}

# Slot and profile names become directory names, so reject path separators,
# Windows-invalid characters and control characters ("a/b" would nest folders).
_BAD_NAME_CHARS = set('<>:"/\\|?*') | {chr(c) for c in range(32)}


def validate_entry_name(name: str) -> str:
    """Return the trimmed name, or raise ValueError with a user-facing message."""
    name = name.strip()
    if not name:
        raise ValueError("Name cannot be empty")
    if len(name) > 120:
        raise ValueError("Name is too long")
    if any(c in _BAD_NAME_CHARS for c in name) or name in (".", "..") or name.endswith("."):
        raise ValueError("Name contains characters that are not allowed")
    return name


@dataclass
class GameConfig:
    name: str
    save_path: str                           # "file" and "folder" modes
    save_mode: str = "file"                  # "file" | "files" | "folder"
    save_paths: list[str] = field(default_factory=list)  # "files" mode


@dataclass
class SaveSlot:
    name: str
    game: str
    profile: str
    path: Path
    date_created: Optional[datetime]
    date_modified: Optional[datetime]
    notes: str
    save_file: Optional[str]  # None for folder/files modes
    video_url: str = ""


# JSON helpers

def _read_json_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to read JSON: %s", path)
        return {}


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=4), encoding="utf-8")


def _timestamps(created: datetime, modified: datetime) -> dict:
    return {
        "created": created.isoformat(timespec="seconds"),
        "modified": modified.isoformat(timespec="seconds"),
    }


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        logger.warning("Invalid ISO datetime in metadata: %r", value)
        return None


# Games

def _game_dirs() -> list[Path]:
    if not SAVES_DIR.exists():
        return []
    return sorted(
        (d for d in SAVES_DIR.iterdir() if d.is_dir() and not d.name.startswith("_")),
        key=lambda d: d.name.lower(),
    )


def find_unconfigured_games() -> list[str]:
    """Return names of game directories that exist but have no game.json."""
    return [d.name for d in _game_dirs() if not (d / _GAME_CONFIG).exists()]


def load_games() -> list[GameConfig]:
    games = []
    for game_dir in _game_dirs():
        data = _read_json_dict(game_dir / _GAME_CONFIG)
        if not data.get("active", True):
            continue
        games.append(GameConfig(
            name=game_dir.name,
            save_path=data.get("save_path", ""),
            save_mode=data.get("save_mode", "file"),
            save_paths=data.get("save_paths", []),
        ))
    logger.info("Loaded %d game config(s) from saves directory", len(games))
    return games


def save_game_config(game_cfg: GameConfig) -> None:
    game_dir = SAVES_DIR / game_cfg.name
    game_dir.mkdir(parents=True, exist_ok=True)
    data: dict = {"active": True, "save_mode": game_cfg.save_mode}
    if game_cfg.save_mode == "files":
        data["save_paths"] = game_cfg.save_paths
    else:
        data["save_path"] = game_cfg.save_path
    _write_json(game_dir / _GAME_CONFIG, data)
    logger.info("Wrote game config: game=%r mode=%r", game_cfg.name, game_cfg.save_mode)


def save_games(games: list[GameConfig]) -> None:
    for game_cfg in games:
        save_game_config(game_cfg)


def deactivate_game(name: str) -> None:
    """Hide a game from the game list without deleting its saves."""
    game_dir = SAVES_DIR / name
    if not game_dir.exists():
        return
    data = _read_json_dict(game_dir / _GAME_CONFIG)
    data["active"] = False
    _write_json(game_dir / _GAME_CONFIG, data)
    logger.info("Deactivated game: %r", name)


# Profiles

def load_profiles(game: str) -> list[str]:
    game_dir = SAVES_DIR / game
    if not game or not game_dir.exists():
        return []
    return sorted(p.name for p in game_dir.iterdir() if p.is_dir())


def create_profile(game: str, name: str) -> None:
    logger.info("Creating profile: game=%r profile=%r", game, name)
    (SAVES_DIR / game / name).mkdir(parents=True, exist_ok=False)


def rename_profile(game: str, old_name: str, new_name: str) -> None:
    logger.info("Renaming profile: game=%r %r -> %r", game, old_name, new_name)
    (SAVES_DIR / game / old_name).rename(SAVES_DIR / game / new_name)


def delete_profile(game: str, name: str) -> None:
    logger.info("Deleting profile to trash: game=%r profile=%r", game, name)
    send2trash.send2trash(str(SAVES_DIR / game / name))


# Slots

def _is_save_file(path: Path) -> bool:
    return path.is_file() and path.name not in _RESERVED and not path.name.startswith(".")


def slot_save_files(slot: SaveSlot) -> list[Path]:
    """All save files stored in a slot, regardless of save mode."""
    save_data = slot.path / "save_data"
    if save_data.is_dir():
        return [f for f in save_data.rglob("*") if f.is_file()]
    return [f for f in slot.path.iterdir() if _is_save_file(f)]


def load_slots(game: str, profile: str) -> list[SaveSlot]:
    profile_dir = SAVES_DIR / game / profile
    if not profile_dir.exists():
        return []
    slots = []
    for slot_dir in sorted(profile_dir.iterdir()):
        if slot_dir.is_dir() and (slot := _read_slot(slot_dir, game, profile)):
            slots.append(slot)
    logger.debug("Loaded %d slot(s) for game=%r profile=%r", len(slots), game, profile)
    return slots


def load_sorted_slots(game: str, profile: str, sort: str, desc: bool) -> list[SaveSlot]:
    """Load slots in display order. Custom order is re-saved so it tracks added/removed slots."""
    slots = load_slots(game, profile)
    if sort == "name":
        slots.sort(key=lambda s: s.name.lower(), reverse=desc)
    elif sort == "created":
        slots.sort(key=lambda s: s.date_created or datetime.min, reverse=desc)
    elif sort == "modified":
        slots.sort(key=lambda s: s.date_modified or s.date_created or datetime.min, reverse=desc)
    elif sort == "custom":
        order = {name: i for i, name in enumerate(load_slot_order(game, profile))}
        slots.sort(key=lambda s: order.get(s.name, len(order)))
        save_slot_order(game, profile, [s.name for s in slots])
    return slots


def _read_slot(slot_dir: Path, game: str, profile: str) -> Optional[SaveSlot]:
    meta_file = slot_dir / "meta.json"
    notes_file = slot_dir / "notes.txt"
    has_folder = (slot_dir / "save_data").is_dir()
    save_file = None if has_folder else next(
        (f.name for f in slot_dir.iterdir() if _is_save_file(f)), None
    )

    # An empty folder is only a slot if it was explicitly created (has meta.json).
    if not has_folder and save_file is None and not meta_file.exists():
        return None

    if not meta_file.exists():
        logger.info("Creating missing metadata for slot: %s", slot_dir)
        if save_file:
            stat = (slot_dir / save_file).stat()
            created = datetime.fromtimestamp(getattr(stat, "st_birthtime", stat.st_ctime))
            modified = datetime.fromtimestamp(stat.st_mtime)
        else:
            created = modified = datetime.now()
        _write_json(meta_file, _timestamps(created, modified))

    if not notes_file.exists():
        notes_file.write_text("", encoding="utf-8")

    meta = _read_json_dict(meta_file)
    return SaveSlot(
        name=slot_dir.name,
        game=game,
        profile=profile,
        path=slot_dir,
        date_created=_parse_iso(meta.get("created")),
        date_modified=_parse_iso(meta.get("modified")),
        notes=notes_file.read_text(encoding="utf-8").strip(),
        save_file=save_file,
        video_url=meta.get("video_url", ""),
    )


def _update_meta(meta_file: Path, updates: dict) -> None:
    meta = _read_json_dict(meta_file)
    meta.update(updates)
    _write_json(meta_file, meta)


def save_notes(slot: SaveSlot, text: str) -> None:
    (slot.path / "notes.txt").write_text(text, encoding="utf-8")
    slot.notes = text


def save_video_url(slot: SaveSlot, url: str) -> None:
    url = url.strip()
    _update_meta(slot.path / "meta.json", {"video_url": url})
    slot.video_url = url


def rename_slot(slot: SaveSlot, new_name: str) -> None:
    """Rename a slot's directory and update the slot object in place."""
    logger.info("Renaming slot: game=%r profile=%r %r -> %r",
                slot.game, slot.profile, slot.name, new_name)
    new_path = slot.path.parent / new_name
    slot.path.rename(new_path)
    slot.name = new_name
    slot.path = new_path


def delete_slot(slot: SaveSlot, soft: bool = False) -> None:
    """Delete a slot; soft sends it to the system trash instead."""
    logger.info("Deleting slot: game=%r profile=%r slot=%r soft=%s",
                slot.game, slot.profile, slot.name, soft)
    if soft:
        send2trash.send2trash(str(slot.path))
    else:
        shutil.rmtree(slot.path)


def _unique_name(folder: Path, base: str) -> str:
    name, n = base, 2
    while (folder / name).exists():
        name = f"{base} {n}"
        n += 1
    return name


def auto_slot_name(game: str, profile: str) -> str:
    return _unique_name(SAVES_DIR / game / profile, "new save")


def duplicate_slot_name(game: str, profile: str, original_name: str) -> str:
    return _unique_name(SAVES_DIR / game / profile, f"{original_name} copy")


def copy_slot_to_profile(slot: SaveSlot, target_profile: str, new_name: str) -> SaveSlot:
    """Copy a slot (with its notes) into a profile of the same game, with fresh timestamps."""
    logger.info("Copying slot: game=%r %r/%r -> %r/%r",
                slot.game, slot.profile, slot.name, target_profile, new_name)
    new_dir = SAVES_DIR / slot.game / target_profile / new_name
    shutil.copytree(slot.path, new_dir)
    now = datetime.now()
    _update_meta(new_dir / "meta.json", _timestamps(now, now))
    return _read_slot(new_dir, slot.game, target_profile)


def duplicate_slot(slot: SaveSlot, new_name: str) -> SaveSlot:
    return copy_slot_to_profile(slot, slot.profile, new_name)


def load_slot_order(game: str, profile: str) -> list[str]:
    order_file = SAVES_DIR / game / profile / "order.json"
    if not order_file.exists():
        return []
    try:
        with open(order_file, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to read slot order: %s", order_file)
        return []


def save_slot_order(game: str, profile: str, names: list[str]) -> None:
    _write_json(SAVES_DIR / game / profile / "order.json", names)


# Copying between slots and the live game save.
#
# A slot or snapshot folder holds the save file itself ("file" mode), each
# listed file ("files" mode), or a save_data/ copy of the folder ("folder" mode).

def _has_save_path(game_cfg: GameConfig) -> bool:
    return bool(game_cfg.save_paths if game_cfg.save_mode == "files" else game_cfg.save_path)


def _live_save_exists(game_cfg: GameConfig) -> bool:
    if game_cfg.save_mode == "files":
        return any(Path(p).exists() for p in game_cfg.save_paths)
    return bool(game_cfg.save_path) and Path(game_cfg.save_path).exists()


def _copy_file(src: Path, dst: Path) -> None:
    logger.debug("Copying %s -> %s", src, dst)
    shutil.copy2(src, dst)


def _replace_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    logger.debug("Copying folder %s -> %s", src, dst)
    shutil.copytree(src, dst)


def _copy_live_save(game_cfg: GameConfig, dest: Path, file_name: Optional[str] = None) -> None:
    """Copy the live save into dest. file_name overrides the stored name in "file" mode."""
    dest.mkdir(parents=True, exist_ok=True)
    if game_cfg.save_mode == "file":
        src = Path(game_cfg.save_path)
        _copy_file(src, dest / (file_name or src.name))
    elif game_cfg.save_mode == "files":
        for src in map(Path, game_cfg.save_paths):
            if src.is_file():
                _copy_file(src, dest / src.name)
            else:
                logger.warning("Configured save file missing: %s", src)
    elif game_cfg.save_mode == "folder":
        _replace_tree(Path(game_cfg.save_path), dest / "save_data")


def _copy_to_live(src_dir: Path, game_cfg: GameConfig, file_name: Optional[str]) -> None:
    """Copy a slot or snapshot folder over the live save. file_name is used in "file" mode."""
    if game_cfg.save_mode == "file":
        if not file_name or not (src_dir / file_name).is_file():
            raise FileNotFoundError(f"No save file in {src_dir}")
        _copy_file(src_dir / file_name, Path(game_cfg.save_path))
    elif game_cfg.save_mode == "files":
        for dst in map(Path, game_cfg.save_paths):
            src = src_dir / dst.name
            if src.exists():
                _copy_file(src, dst)
            else:
                logger.warning("Save file missing from %s: %s", src_dir, dst.name)
    elif game_cfg.save_mode == "folder":
        if not (src_dir / "save_data").is_dir():
            raise FileNotFoundError(f"No save_data folder in {src_dir}")
        _replace_tree(src_dir / "save_data", Path(game_cfg.save_path))


def import_save(game: str, profile: str, slot_name: str, game_cfg: GameConfig) -> SaveSlot:
    """Copy the game's live save into a new slot."""
    slot_dir = SAVES_DIR / game / profile / slot_name
    logger.info("Importing save: game=%r profile=%r slot=%r mode=%s",
                game, profile, slot_name, game_cfg.save_mode)
    slot_dir.mkdir(parents=True, exist_ok=False)
    _copy_live_save(game_cfg, slot_dir)
    now = datetime.now()
    _write_json(slot_dir / "meta.json", _timestamps(now, now))
    (slot_dir / "notes.txt").write_text("", encoding="utf-8")
    return _read_slot(slot_dir, game, profile)


def replace_save(slot: SaveSlot, game_cfg: GameConfig) -> None:
    """Overwrite a slot's contents with the game's live save."""
    logger.info("Replacing slot from live save: game=%r profile=%r slot=%r mode=%s",
                slot.game, slot.profile, slot.name, game_cfg.save_mode)
    _copy_live_save(game_cfg, slot.path, file_name=slot.save_file)
    now = datetime.now()
    meta_file = slot.path / "meta.json"
    meta = _read_json_dict(meta_file)
    created = _parse_iso(meta.get("created")) or now
    _update_meta(meta_file, _timestamps(created, now))
    slot.date_modified = now


def load_save(slot: SaveSlot, game_cfg: GameConfig, *, make_backup: bool = True) -> None:
    """Copy a slot's save over the game's live save, backing up the live save first."""
    logger.info("Loading slot to live save: game=%r profile=%r slot=%r mode=%s make_backup=%s",
                slot.game, slot.profile, slot.name, game_cfg.save_mode, make_backup)
    if not _has_save_path(game_cfg):
        raise ValueError(f"Save path is not configured for game {game_cfg.name!r}")
    if make_backup:
        try:
            _rotating_backup(game_cfg, _BACKUPS_DIR)
        except OSError:
            logger.exception("Failed to back up live save before load; continuing")
    _copy_to_live(slot.path, game_cfg, slot.save_file)


def take_run_backup(game_cfg: GameConfig) -> None:
    _rotating_backup(game_cfg, _RUN_BACKUPS_DIR)


def _rotating_backup(game_cfg: GameConfig, dir_name: str) -> None:
    """Snapshot the live save into a timestamped folder, keeping the newest few."""
    if not _live_save_exists(game_cfg):
        logger.warning("Skipping %s backup; no live save for game=%r", dir_name, game_cfg.name)
        return
    root = SAVES_DIR / dir_name / game_cfg.name
    dest = root / datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
    logger.info("Backing up live save: %s", dest)
    _copy_live_save(game_cfg, dest)
    for old in sorted(d for d in root.iterdir() if d.is_dir())[:-_MAX_BACKUPS]:
        logger.info("Pruning old backup: %s", old)
        shutil.rmtree(old)


def snapshot_practice_start(game_cfg: GameConfig) -> None:
    """Save the live save from before practice mode, replacing any previous snapshot."""
    if not _live_save_exists(game_cfg):
        logger.warning("Skipping practice-start snapshot; no live save for game=%r", game_cfg.name)
        return
    dest = SAVES_DIR / _PRACTICE_START_DIR / game_cfg.name
    if dest.exists():
        shutil.rmtree(dest)
    logger.info("Taking practice-start snapshot: %s", dest)
    _copy_live_save(game_cfg, dest)


def restore_practice_start(game_cfg: GameConfig) -> None:
    """Put the pre-practice snapshot back as the live save."""
    src_dir = SAVES_DIR / _PRACTICE_START_DIR / game_cfg.name
    if not src_dir.exists() or not _has_save_path(game_cfg):
        logger.warning("No practice-start snapshot to restore for game=%r", game_cfg.name)
        return
    logger.info("Restoring practice-start snapshot: %s", src_dir)
    first_file = next((f.name for f in sorted(src_dir.iterdir()) if f.is_file()), None)
    _copy_to_live(src_dir, game_cfg, first_file)
