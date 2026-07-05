import json
import logging
from dataclasses import dataclass, asdict

from app_paths import app_dir, migrate_from_bundle

migrate_from_bundle("config.json")

_CONFIG_FILE = app_dir() / "config.json"
logger = logging.getLogger(__name__)


@dataclass
class Config:
    confirm_delete: bool = True
    confirm_replace: bool = True
    confirm_lock_slot: bool = True
    auto_name_imports: bool = True
    hide_paths: bool = False
    slot_sort: str = "name"  # "name" | "created" | "modified" | "custom"
    slot_sort_desc: bool = True  # True = descending (newest first / Z→A)
    last_game: str = ""
    last_profile: str = ""
    last_slot: str = ""
    hotkey_import: str = "F5"
    hotkey_load: str = "F9"
    hotkey_replace: str = ""
    hotkey_ro_toggle: str = "F6"
    hotkey_next_slot: str = ""
    hotkey_prev_slot: str = ""
    global_hotkeys_enabled: bool = False
    protect_warning_acknowledged: bool = False
    soft_delete: bool = True
    hide_details: bool = False
    window_width: int = 0
    window_height: int = 0
    check_updates_on_startup: bool = True


def load_config() -> Config:
    if not _CONFIG_FILE.exists():
        logger.info("Config file not found, using defaults: %s", _CONFIG_FILE)
        return Config()
    try:
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Loaded config: %s", _CONFIG_FILE)
        return Config(
            confirm_delete=data.get("confirm_delete", True),
            confirm_replace=data.get("confirm_replace", True),
            confirm_lock_slot=data.get("confirm_lock_slot", True),
            auto_name_imports=data.get("auto_name_imports", True),
            hide_paths=data.get("hide_paths", False),
            slot_sort=data.get("slot_sort", "name"),
            slot_sort_desc=data.get("slot_sort_desc", True),
            last_game=data.get("last_game", ""),
            last_profile=data.get("last_profile", ""),
            last_slot=data.get("last_slot", ""),
            hotkey_import=data.get("hotkey_import", "F5"),
            hotkey_load=data.get("hotkey_load", "F9"),
            hotkey_replace=data.get("hotkey_replace", ""),
            hotkey_ro_toggle=data.get("hotkey_ro_toggle", "F6"),
            hotkey_next_slot=data.get("hotkey_next_slot", ""),
            hotkey_prev_slot=data.get("hotkey_prev_slot", ""),
            global_hotkeys_enabled=data.get("global_hotkeys_enabled", False),
            protect_warning_acknowledged=data.get("protect_warning_acknowledged", False),
            soft_delete=data.get("soft_delete", True),
            hide_details=data.get("hide_details", False),
            window_width=data.get("window_width", 0),
            window_height=data.get("window_height", 0),
            check_updates_on_startup=data.get("check_updates_on_startup", True),
        )
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to load config, using defaults: %s", _CONFIG_FILE)
        return Config()


def save_config(cfg: Config) -> None:
    logger.debug("Saving config: %s", _CONFIG_FILE)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=4)
