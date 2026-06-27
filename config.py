import json
from dataclasses import dataclass, asdict
from pathlib import Path

_CONFIG_FILE = Path(__file__).parent / "config.json"


@dataclass
class Config:
    confirm_delete: bool = True
    confirm_replace: bool = True
    auto_name_imports: bool = False


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
        )
    except (json.JSONDecodeError, OSError):
        return Config()


def save_config(cfg: Config) -> None:
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=4)
