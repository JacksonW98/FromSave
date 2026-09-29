import json
import logging
from dataclasses import asdict, dataclass, fields

from app_paths import app_dir, migrate_from_bundle

migrate_from_bundle("config.json")

CONFIG_FILE = app_dir() / "config.json"
logger = logging.getLogger(__name__)


@dataclass
class Config:
    confirm_delete: bool = True
    confirm_replace: bool = True
    confirm_lock_slot: bool = True
    auto_name_imports: bool = True
    hide_paths: bool = False
    slot_sort: str = "name"  # "name" | "created" | "modified" | "custom"
    slot_sort_desc: bool = True
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
    hotkey_toggle_overlay: str = "Ins"
    overlay_hotkey_import: str = "F5"
    overlay_hotkey_load: str = "F9"
    overlay_hotkey_replace: str = ""
    overlay_hotkey_rename: str = "F2"
    overlay_hotkey_ro_toggle: str = "F6"
    overlay_hotkey_next_slot: str = "Ctrl+Down"
    overlay_hotkey_prev_slot: str = "Ctrl+Up"
    overlay_opacity: float = 0.85
    overlay_pos_x: int = -1
    overlay_pos_y: int = -1
    companion_enabled: bool = False
    companion_port: int = 8765
    companion_token: str = ""
    companion_firewall_notice_shown: bool = False


def load_config() -> Config:
    if not CONFIG_FILE.exists():
        logger.info("Config file not found, using defaults: %s", CONFIG_FILE)
        return Config()
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to load config, using defaults: %s", CONFIG_FILE)
        return Config()
    logger.info("Loaded config: %s", CONFIG_FILE)
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})


def save_config(cfg: Config) -> None:
    logger.debug("Saving config: %s", CONFIG_FILE)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=4)
