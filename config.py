import json
from dataclasses import dataclass, asdict
from pathlib import Path

_CONFIG_FILE = Path(__file__).parent / "config.json"


@dataclass
class Config:
    confirm_delete: bool = True
    confirm_replace: bool = True
    auto_name_imports: bool = False
    show_save_path: bool = True
    slot_sort: str = "modified"  # "name" | "created" | "modified" | "custom"
    slot_sort_desc: bool = True  # True = descending (newest first / Z→A)
    last_game: str = ""
    last_profile: str = ""
    last_slot: str = ""
    hotkey_import: str = "F5"
    hotkey_load: str = "F9"
    hotkey_ro_toggle: str = "F6"
    soft_delete: bool = False
    compact_list: bool = False


def load_config() -> Config:
    if not _CONFIG_FILE.exists():
        return Config()
    try:
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return Config(
            confirm_delete=data.get("confirm_delete", True),
            confirm_replace=data.get("confirm_replace", True),
            auto_name_imports=data.get("auto_name_imports", False),
            show_save_path=data.get("show_save_path", True),
            slot_sort=data.get("slot_sort", "modified"),
            slot_sort_desc=data.get("slot_sort_desc", True),
            last_game=data.get("last_game", ""),
            last_profile=data.get("last_profile", ""),
            last_slot=data.get("last_slot", ""),
            hotkey_import=data.get("hotkey_import", "F5"),
            hotkey_load=data.get("hotkey_load", "F9"),
            hotkey_ro_toggle=data.get("hotkey_ro_toggle", "F6"),
            soft_delete=data.get("soft_delete", False),
            compact_list=data.get("compact_list", False),
        )
    except (json.JSONDecodeError, OSError):
        return Config()


def save_config(cfg: Config) -> None:
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=4)
