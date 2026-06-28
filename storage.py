import json
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


def load_games() -> list[GameConfig]:
    if not GAMES_FILE.exists():
        return []
    with open(GAMES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return [
        GameConfig(
            name=name,
            save_path=cfg.get("save_path", ""),
            save_mode=cfg.get("save_mode", "file"),
            save_paths=cfg.get("save_paths", []),
        )
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
        return None

    if not meta_file.exists():
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


def import_save(game: str, profile: str, slot_name: str, game_cfg: GameConfig) -> SaveSlot:
    """Copy the game's live save into a new slot folder."""
    slot_dir = SAVES_DIR / game / profile / slot_name
    slot_dir.mkdir(parents=True, exist_ok=False)

    mode = game_cfg.save_mode
    save_file: Optional[str] = None

    if mode == "file":
        src = Path(game_cfg.save_path)
        shutil.copy2(src, slot_dir / src.name)
        save_file = src.name
    elif mode == "files":
        for path_str in game_cfg.save_paths:
            src = Path(path_str)
            if src.is_file():
                shutil.copy2(src, slot_dir / src.name)
    elif mode == "folder":
        shutil.copytree(Path(game_cfg.save_path), slot_dir / "save_data")

    now = datetime.now()
    meta = {
        "created": now.isoformat(timespec="seconds"),
        "modified": now.isoformat(timespec="seconds"),
    }
    (slot_dir / "meta.json").write_text(json.dumps(meta, indent=4), encoding="utf-8")
    (slot_dir / "notes.txt").write_text("", encoding="utf-8")

    return SaveSlot(
        name=slot_name,
        game=game,
        profile=profile,
        path=slot_dir,
        date_created=now,
        date_modified=now,
        notes="",
        save_file=save_file,
    )


def replace_save(slot: SaveSlot, game_cfg: GameConfig) -> None:
    """Overwrite a slot's contents with the game's live save."""
    mode = game_cfg.save_mode

    if mode == "file":
        src = Path(game_cfg.save_path)
        shutil.copy2(src, slot.path / slot.save_file)
    elif mode == "files":
        for path_str in game_cfg.save_paths:
            src = Path(path_str)
            if src.is_file():
                shutil.copy2(src, slot.path / src.name)
    elif mode == "folder":
        save_data = slot.path / "save_data"
        if save_data.exists():
            shutil.rmtree(save_data)
        shutil.copytree(Path(game_cfg.save_path), save_data)

    now = datetime.now()
    _update_meta_modified(slot.path / "meta.json", now)
    slot.date_modified = now


def load_save(slot: SaveSlot, game_cfg: GameConfig) -> None:
    """Copy a slot's save back to the game's save path."""
    mode = game_cfg.save_mode

    if mode == "file":
        shutil.copy2(slot.path / slot.save_file, Path(game_cfg.save_path))
    elif mode == "files":
        for path_str in game_cfg.save_paths:
            dst = Path(path_str)
            slot_file = slot.path / dst.name
            if slot_file.exists():
                shutil.copy2(slot_file, dst)
    elif mode == "folder":
        dest = Path(game_cfg.save_path)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(slot.path / "save_data", dest)


def create_profile(game: str, name: str) -> None:
    (SAVES_DIR / game / name).mkdir(parents=True, exist_ok=False)


def rename_profile(game: str, old_name: str, new_name: str) -> None:
    (SAVES_DIR / game / old_name).rename(SAVES_DIR / game / new_name)


def delete_profile(game: str, name: str) -> None:
    shutil.rmtree(SAVES_DIR / game / name)


def delete_slot(slot: SaveSlot) -> None:
    """Permanently delete a slot directory and all its contents."""
    shutil.rmtree(slot.path)


def rename_slot(slot: SaveSlot, new_name: str) -> None:
    """Rename a slot's directory and update the slot object in-place."""
    new_path = slot.path.parent / new_name
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
    new_dir = slot.path.parent / new_name
    shutil.copytree(slot.path, new_dir)
    now = datetime.now()
    (new_dir / "meta.json").write_text(
        json.dumps({"created": now.isoformat(timespec="seconds"),
                    "modified": now.isoformat(timespec="seconds")}, indent=4),
        encoding="utf-8",
    )
    return _read_slot(new_dir, slot.game, slot.profile)


def copy_slot_to_profile(slot: SaveSlot, target_profile: str, new_name: str) -> SaveSlot:
    """Copy a slot (with its notes) to a different profile under the same game."""
    new_dir = SAVES_DIR / slot.game / target_profile / new_name
    shutil.copytree(slot.path, new_dir)
    now = datetime.now()
    (new_dir / "meta.json").write_text(
        json.dumps({"created": now.isoformat(timespec="seconds"),
                    "modified": now.isoformat(timespec="seconds")}, indent=4),
        encoding="utf-8",
    )
    return _read_slot(new_dir, slot.game, target_profile)


def save_games(games: list[GameConfig]) -> None:
    """Write updated game configs back to games.json."""
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
        return []


def save_slot_order(game: str, profile: str, names: list[str]) -> None:
    order_file = SAVES_DIR / game / profile / "order.json"
    with open(order_file, "w", encoding="utf-8") as f:
        json.dump(names, f, indent=4)


def _update_meta_modified(meta_file: Path, now: datetime) -> None:
    date_created, _ = _parse_meta(meta_file)
    meta = {
        "created": (date_created or now).isoformat(timespec="seconds"),
        "modified": now.isoformat(timespec="seconds"),
    }
    meta_file.write_text(json.dumps(meta, indent=4), encoding="utf-8")


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
