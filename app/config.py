from __future__ import annotations

import os
from pathlib import Path

TEMPLATES_DIR = Path(os.environ.get("TEMPLATES_DIR", "/opt/templates"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")


def installer_readme_path() -> Path:
    """README shipped with the installer product (Docker: /opt/installer/README.md)."""
    env = os.environ.get("INSTALLER_README", "").strip()
    candidates = [
        Path(env) if env else None,
        Path("/opt/installer/README.md"),
        Path(__file__).resolve().parent.parent / "README.md",
    ]
    for path in candidates:
        if path is not None and path.is_file():
            return path
    raise FileNotFoundError("installer README not found")


def instance_dir(instance_id: str) -> Path:
    return DATA_DIR / "instances" / instance_id


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
