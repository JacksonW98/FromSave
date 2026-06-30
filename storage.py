import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent
SAVES_DIR = _ROOT / "saves"
GAMES_FILE = _ROOT / "games.json"

_RESERVED = {"meta.json", "notes.txt"}
logger = logging.getLogger(__name__)


@dataclass
class GameConfig:
    name: str
    save_path: str                           # used by "file" and "folder" modes
    save_mode: str = "file"                  # "file" | "files" | "folder"
    save_paths: list[str] = field(default_factory=list)  # used by "files" mode


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


def load_games() -> list[GameConfig]:
    if not GAMES_FILE.exists():
        logger.info("Games file not found: %s", GAMES_FILE)
        return []
    with open(GAMES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    games = [
        GameConfig(
            name=name,
            save_path=cfg.get("save_path", ""),
            save_mode=cfg.get("save_mode", "file"),
            save_paths=cfg.get("save_paths", []),
        )
        for name, cfg in data.items()
    ]
    logger.info("Loaded %d game config(s) from %s", len(games), GAMES_FILE)
    return games


def load_profiles(game: str) -> list[str]:
    game_dir = SAVES_DIR / game
    if not game_dir.exists():
        logger.debug("No profiles directory for game=%r: %s", game, game_dir)
        return []
    profiles = sorted(p.name for p in game_dir.iterdir() if p.is_dir())
    logger.debug("Loaded %d profile(s) for game=%r", len(profiles), game)
    return profiles


def load_slots(game: str, profile: str) -> list[SaveSlot]:
    profile_dir = SAVES_DIR / game / profile
    if not profile_dir.exists():
        logger.debug("No slots directory for game=%r profile=%r: %s", game, profile, profile_dir)
        return []
    slots = []
    for slot_dir in sorted(profile_dir.iterdir()):
        if not slot_dir.is_dir():
            continue
        slot = _read_slot(slot_dir, game, profile)
        if slot is not None:
            slots.append(slot)
    logger.debug("Loaded %d slot(s) for game=%r profile=%r", len(slots), game, profile)
    return slots


def _read_slot(slot_dir: Path, game: str, profile: str) -> Optional[SaveSlot]:
    meta_file = slot_dir / "meta.json"
    notes_file = slot_dir / "notes.txt"

    # folder-mode slots store content in save_data/
    save_data_dir = slot_dir / "save_data"
    has_folder = save_data_dir.exists() and save_data_dir.is_dir()

    save_file: Optional[str] = None
    if not has_folder:
        save_file = next(
            (
                f.name for f in slot_dir.iterdir()
                if f.is_file() and f.name not in _RESERVED and not f.name.startswith(".")
            ),
            None,
        )

    # Slot is only valid if it has content or was explicitly created (meta exists)
    if not has_folder and save_file is None and not meta_file.exists():
        logger.debug("Ignoring empty slot directory without metadata: %s", slot_dir)
        return None

    if not meta_file.exists():
        logger.info("Creating missing metadata for slot: %s", slot_dir)
        if save_file:
            _create_meta(meta_file, (slot_dir / save_file).stat())
        else:
            now = datetime.now()
            meta = {
                "created": now.isoformat(timespec="seconds"),
                "modified": now.isoformat(timespec="seconds"),
            }
            meta_file.write_text(json.dumps(meta, indent=4), encoding="utf-8")

    if not notes_file.exists():
        notes_file.write_text("", encoding="utf-8")

    meta = _read_meta(meta_file)
    date_created = _parse_iso(meta.get("created"))
    date_modified = _parse_iso(meta.get("modified"))
    notes = notes_file.read_text(encoding="utf-8").strip()
    video_url = meta.get("video_url", "")

    return SaveSlot(
        name=slot_dir.name,
        game=game,
        profile=profile,
        path=slot_dir,
        date_created=date_created,
        date_modified=date_modified,
        notes=notes,
        save_file=save_file,
        video_url=video_url,
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


def _read_meta(meta_file: Path) -> dict:
    try:
        with open(meta_file, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to read metadata: %s", meta_file)
        return {}


def _write_meta(meta_file: Path, updates: dict) -> None:
    meta = _read_meta(meta_file)
    meta.update(updates)
    meta_file.write_text(json.dumps(meta, indent=4), encoding="utf-8")


def save_notes(slot: SaveSlot, text: str) -> None:
    notes_file = slot.path / "notes.txt"
    logger.debug("Saving notes for game=%r profile=%r slot=%r", slot.game, slot.profile, slot.name)
    notes_file.write_text(text, encoding="utf-8")
    slot.notes = text


def save_video_url(slot: SaveSlot, url: str) -> None:
    url = url.strip()
    logger.debug("Saving video URL for game=%r profile=%r slot=%r has_url=%s",
                 slot.game, slot.profile, slot.name, bool(url))
    _write_meta(slot.path / "meta.json", {"video_url": url})
    slot.video_url = url


def import_save(game: str, profile: str, slot_name: str, game_cfg: GameConfig) -> SaveSlot:
    """Copy the game's live save into a new slot folder."""
    slot_dir = SAVES_DIR / game / profile / slot_name
    logger.info("Importing save: game=%r profile=%r slot=%r mode=%s dest=%s",
                game, profile, slot_name, game_cfg.save_mode, slot_dir)
    slot_dir.mkdir(parents=True, exist_ok=False)

    mode = game_cfg.save_mode
    save_file: Optional[str] = None

    if mode == "file":
        src = Path(game_cfg.save_path)
        logger.debug("Copying live save file: %s -> %s", src, slot_dir / src.name)
        shutil.copy2(src, slot_dir / src.name)
        save_file = src.name
    elif mode == "files":
        for path_str in game_cfg.save_paths:
            src = Path(path_str)
            if src.is_file():
                logger.debug("Copying live save file: %s -> %s", src, slot_dir / src.name)
                shutil.copy2(src, slot_dir / src.name)
            else:
                logger.warning("Configured save file missing during import: %s", src)
    elif mode == "folder":
        logger.debug("Copying live save folder: %s -> %s", game_cfg.save_path, slot_dir / "save_data")
        shutil.copytree(Path(game_cfg.save_path), slot_dir / "save_data")

    now = datetime.now()
    meta = {
        "created": now.isoformat(timespec="seconds"),
        "modified": now.isoformat(timespec="seconds"),
    }
    (slot_dir / "meta.json").write_text(json.dumps(meta, indent=4), encoding="utf-8")
    (slot_dir / "notes.txt").write_text("", encoding="utf-8")

    logger.info("Imported save slot: game=%r profile=%r slot=%r", game, profile, slot_name)
    return SaveSlot(
        name=slot_name,
        game=game,
        profile=profile,
        path=slot_dir,
        date_created=now,
        date_modified=now,
        notes="",
        save_file=save_file,
        video_url="",
    )


def replace_save(slot: SaveSlot, game_cfg: GameConfig) -> None:
    """Overwrite a slot's contents with the game's live save."""
    mode = game_cfg.save_mode
    logger.info("Replacing slot from live save: game=%r profile=%r slot=%r mode=%s",
                slot.game, slot.profile, slot.name, mode)

    if mode == "file":
        src = Path(game_cfg.save_path)
        logger.debug("Copying live save file: %s -> %s", src, slot.path / slot.save_file)
        shutil.copy2(src, slot.path / slot.save_file)
    elif mode == "files":
        for path_str in game_cfg.save_paths:
            src = Path(path_str)
            if src.is_file():
                logger.debug("Copying live save file: %s -> %s", src, slot.path / src.name)
                shutil.copy2(src, slot.path / src.name)
            else:
                logger.warning("Configured save file missing during replace: %s", src)
    elif mode == "folder":
        save_data = slot.path / "save_data"
        if save_data.exists():
            logger.debug("Removing old slot save folder: %s", save_data)
            shutil.rmtree(save_data)
        logger.debug("Copying live save folder: %s -> %s", game_cfg.save_path, save_data)
        shutil.copytree(Path(game_cfg.save_path), save_data)

    now = datetime.now()
    _update_meta_modified(slot.path / "meta.json", now)
    slot.date_modified = now


_BACKUPS_DIR_NAME = "_backups"
_MAX_LOAD_BACKUPS = 3


def load_save(slot: SaveSlot, game_cfg: GameConfig, *, make_backup: bool = True) -> None:
    """Copy a slot's save back to the game's save path."""
    logger.info("Loading slot to live save: game=%r profile=%r slot=%r mode=%s make_backup=%s",
                slot.game, slot.profile, slot.name, game_cfg.save_mode, make_backup)
    if make_backup:
        try:
            _backup_live_save(game_cfg)
        except OSError:
            logger.exception("Failed to back up live save before load; continuing")
            pass  # best-effort — don't block the load if backup fails

    mode = game_cfg.save_mode

    if mode == "file":
        logger.debug("Copying slot save file: %s -> %s", slot.path / slot.save_file, game_cfg.save_path)
        shutil.copy2(slot.path / slot.save_file, Path(game_cfg.save_path))
    elif mode == "files":
        for path_str in game_cfg.save_paths:
            dst = Path(path_str)
            slot_file = slot.path / dst.name
            if slot_file.exists():
                logger.debug("Copying slot save file: %s -> %s", slot_file, dst)
                shutil.copy2(slot_file, dst)
            else:
                logger.warning("Slot file missing during load: %s", slot_file)
    elif mode == "folder":
        dest = Path(game_cfg.save_path)
        if dest.exists():
            logger.debug("Removing live save folder before load: %s", dest)
            shutil.rmtree(dest)
        logger.debug("Copying slot save folder: %s -> %s", slot.path / "save_data", dest)
        shutil.copytree(slot.path / "save_data", dest)


def _backup_live_save(game_cfg: GameConfig) -> None:
    """Snapshot the live game save before it is overwritten by load_save."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
    backup_dir = SAVES_DIR / _BACKUPS_DIR_NAME / game_cfg.name / timestamp
    mode = game_cfg.save_mode

    if mode == "file":
        src = Path(game_cfg.save_path)
        if not src.exists():
            logger.warning("Skipping load backup; live save file missing: %s", src)
            return
        backup_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Backing up live save file: %s -> %s", src, backup_dir / src.name)
        shutil.copy2(src, backup_dir / src.name)
    elif mode == "files":
        existing = [Path(p) for p in game_cfg.save_paths if Path(p).exists()]
        if not existing:
            logger.warning("Skipping load backup; no configured save files exist for game=%r", game_cfg.name)
            return
        backup_dir.mkdir(parents=True, exist_ok=True)
        for src in existing:
            logger.info("Backing up live save file: %s -> %s", src, backup_dir / src.name)
            shutil.copy2(src, backup_dir / src.name)
    elif mode == "folder":
        src = Path(game_cfg.save_path)
        if not src.exists():
            logger.warning("Skipping load backup; live save folder missing: %s", src)
            return
        backup_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Backing up live save folder: %s -> %s", src, backup_dir / "save_data")
        shutil.copytree(src, backup_dir / "save_data")

    _prune_backups(game_cfg.name, _MAX_LOAD_BACKUPS)


def _prune_backups(game_name: str, keep: int) -> None:
    """Delete oldest backup snapshots, retaining only the `keep` most recent."""
    backup_game_dir = SAVES_DIR / _BACKUPS_DIR_NAME / game_name
    if not backup_game_dir.exists():
        return
    dirs = sorted(d for d in backup_game_dir.iterdir() if d.is_dir())
    for old in dirs[:-keep]:
        logger.info("Pruning old load backup: %s", old)
        shutil.rmtree(old)


_RUN_BACKUPS_DIR_NAME = "_run_backups"
_MAX_RUN_BACKUPS = 3


def take_run_backup(game_cfg: GameConfig) -> None:
    """Snapshot the live game save for run mode; keeps the 3 most recent."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_dir = SAVES_DIR / _RUN_BACKUPS_DIR_NAME / game_cfg.name / timestamp
    mode = game_cfg.save_mode

    if mode == "file":
        src = Path(game_cfg.save_path)
        if not src.exists():
            logger.warning("Skipping run backup; live save file missing: %s", src)
            return
        backup_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Taking run backup file: %s -> %s", src, backup_dir / src.name)
        shutil.copy2(src, backup_dir / src.name)
    elif mode == "files":
        existing = [Path(p) for p in game_cfg.save_paths if Path(p).exists()]
        if not existing:
            logger.warning("Skipping run backup; no configured save files exist for game=%r", game_cfg.name)
            return
        backup_dir.mkdir(parents=True, exist_ok=True)
        for src in existing:
            logger.info("Taking run backup file: %s -> %s", src, backup_dir / src.name)
            shutil.copy2(src, backup_dir / src.name)
    elif mode == "folder":
        src = Path(game_cfg.save_path)
        if not src.exists():
            logger.warning("Skipping run backup; live save folder missing: %s", src)
            return
        backup_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Taking run backup folder: %s -> %s", src, backup_dir / "save_data")
        shutil.copytree(src, backup_dir / "save_data")

    _prune_run_backups(game_cfg.name)


def _prune_run_backups(game_name: str) -> None:
    backup_game_dir = SAVES_DIR / _RUN_BACKUPS_DIR_NAME / game_name
    if not backup_game_dir.exists():
        return
    dirs = sorted(d for d in backup_game_dir.iterdir() if d.is_dir())
    for old in dirs[:-_MAX_RUN_BACKUPS]:
        logger.info("Pruning old run backup: %s", old)
        shutil.rmtree(old)


def create_profile(game: str, name: str) -> None:
    logger.info("Creating profile: game=%r profile=%r", game, name)
    (SAVES_DIR / game / name).mkdir(parents=True, exist_ok=False)


def rename_profile(game: str, old_name: str, new_name: str) -> None:
    logger.info("Renaming profile: game=%r %r -> %r", game, old_name, new_name)
    (SAVES_DIR / game / old_name).rename(SAVES_DIR / game / new_name)


def delete_profile(game: str, name: str) -> None:
    logger.info("Deleting profile to trash: game=%r profile=%r", game, name)
    import send2trash
    send2trash.send2trash(str(SAVES_DIR / game / name))


def delete_slot(slot: SaveSlot, soft: bool = False) -> None:
    """Delete a slot. If soft is True, send to system trash instead of deleting permanently."""
    logger.info("Deleting slot: game=%r profile=%r slot=%r soft=%s path=%s",
                slot.game, slot.profile, slot.name, soft, slot.path)
    if soft:
        import send2trash
        send2trash.send2trash(str(slot.path))
    else:
        shutil.rmtree(slot.path)


def rename_slot(slot: SaveSlot, new_name: str) -> None:
    """Rename a slot's directory and update the slot object in-place."""
    new_path = slot.path.parent / new_name
    logger.info("Renaming slot: game=%r profile=%r %r -> %r",
                slot.game, slot.profile, slot.name, new_name)
    slot.path.rename(new_path)
    slot.name = new_name
    slot.path = new_path


def auto_slot_name(game: str, profile: str) -> str:
    """Return the next unused auto-generated slot name for a profile."""
    base = "new save"
    if not (SAVES_DIR / game / profile / base).exists():
        return base
    n = 2
    while (SAVES_DIR / game / profile / f"{base} {n}").exists():
        n += 1
    return f"{base} {n}"


def duplicate_slot_name(game: str, profile: str, original_name: str) -> str:
    """Return a unique 'original copy' / 'original copy 2' name in the given profile."""
    target = SAVES_DIR / game / profile
    base = f"{original_name} copy"
    if not (target / base).exists():
        return base
    n = 2
    while (target / f"{base} {n}").exists():
        n += 1
    return f"{base} {n}"


def duplicate_slot(slot: SaveSlot, new_name: str) -> SaveSlot:
    """Copy a slot to a new name within the same profile."""
    logger.info("Duplicating slot: game=%r profile=%r %r -> %r",
                slot.game, slot.profile, slot.name, new_name)
    new_dir = slot.path.parent / new_name
    shutil.copytree(slot.path, new_dir)
    now = datetime.now()
    _write_meta(new_dir / "meta.json", {
        "created": now.isoformat(timespec="seconds"),
        "modified": now.isoformat(timespec="seconds"),
    })
    return _read_slot(new_dir, slot.game, slot.profile)


def copy_slot_to_profile(slot: SaveSlot, target_profile: str, new_name: str) -> SaveSlot:
    """Copy a slot (with its notes) to a different profile under the same game."""
    logger.info("Copying slot to profile: game=%r %r/%r -> %r/%r",
                slot.game, slot.profile, slot.name, target_profile, new_name)
    new_dir = SAVES_DIR / slot.game / target_profile / new_name
    shutil.copytree(slot.path, new_dir)
    now = datetime.now()
    _write_meta(new_dir / "meta.json", {
        "created": now.isoformat(timespec="seconds"),
        "modified": now.isoformat(timespec="seconds"),
    })
    return _read_slot(new_dir, slot.game, target_profile)


def save_games(games: list[GameConfig]) -> None:
    """Write updated game configs back to games.json."""
    logger.info("Saving %d game config(s) to %s", len(games), GAMES_FILE)
    data = {}
    for g in games:
        if g.save_mode == "files":
            data[g.name] = {"save_mode": "files", "save_paths": g.save_paths}
        else:
            data[g.name] = {"save_mode": g.save_mode, "save_path": g.save_path}
    with open(GAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


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
    order_file = SAVES_DIR / game / profile / "order.json"
    logger.debug("Saving slot order: game=%r profile=%r count=%d", game, profile, len(names))
    with open(order_file, "w", encoding="utf-8") as f:
        json.dump(names, f, indent=4)


def _update_meta_modified(meta_file: Path, now: datetime) -> None:
    meta = _read_meta(meta_file)
    created = _parse_iso(meta.get("created")) or now
    _write_meta(meta_file, {
        "created": created.isoformat(timespec="seconds"),
        "modified": now.isoformat(timespec="seconds"),
    })


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        logger.warning("Invalid ISO datetime in metadata: %r", value)
        return None
