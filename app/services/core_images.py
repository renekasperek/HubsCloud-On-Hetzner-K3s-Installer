from __future__ import annotations

import re
from typing import Literal

CoreAppName = Literal["reticulum", "hubs", "spoke"]
CoreAppImageMode = Literal["default", "pin", "custom"]

CORE_APP_NAMES: tuple[CoreAppName, ...] = ("reticulum", "hubs", "spoke")

CORE_APP_DEFAULTS: dict[CoreAppName, dict[str, str]] = {
    "reticulum": {"repo": "hubsfoundation/reticulum", "default_tag": "stable-latest"},
    "hubs": {"repo": "hubsfoundation/hubs", "default_tag": "stable-latest"},
    "spoke": {"repo": "hubsfoundation/spoke", "default_tag": "stable-latest"},
}

TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# Public image refs only — no spaces; repo path + optional :tag or @digest
IMAGE_RE = re.compile(
    r"^[a-z0-9]([a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*)?(:[A-Za-z0-9][A-Za-z0-9._-]{0,127}|@sha256:[a-f0-9]{64})?$",
    re.IGNORECASE,
)


def normalize_core_app_images(raw: dict | None) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for name in CORE_APP_NAMES:
        entry = (raw or {}).get(name) or {}
        mode = str(entry.get("mode") or "default").strip().lower()
        if mode not in ("default", "pin", "custom"):
            mode = "default"
        out[name] = {
            "mode": mode,
            "tag": str(entry.get("tag") or "").strip(),
            "image": str(entry.get("image") or "").strip(),
        }
    return out


def resolve_core_app_image(app: CoreAppName, settings: dict[str, dict[str, str]] | None) -> str:
    cfg = normalize_core_app_images(settings).get(app, {})
    meta = CORE_APP_DEFAULTS[app]
    mode = cfg.get("mode", "default")
    if mode == "custom":
        return cfg.get("image") or f"{meta['repo']}:{meta['default_tag']}"
    if mode == "pin":
        tag = cfg.get("tag") or meta["default_tag"]
        return f"{meta['repo']}:{tag}"
    return f"{meta['repo']}:{meta['default_tag']}"


def resolve_all_core_app_images(settings: dict[str, dict[str, str]] | None) -> dict[str, str]:
    return {app: resolve_core_app_image(app, settings) for app in CORE_APP_NAMES}


def validate_core_app_images(settings: dict[str, dict[str, str]] | None) -> list[str]:
    errors: list[str] = []
    for app in CORE_APP_NAMES:
        cfg = normalize_core_app_images(settings)[app]
        mode = cfg["mode"]
        label = app.capitalize()
        if mode == "pin":
            tag = cfg["tag"]
            if not tag:
                errors.append(f"{label}: enter a tag to pin (e.g. stable-latest).")
            elif not TAG_RE.match(tag):
                errors.append(f"{label}: invalid tag format.")
        elif mode == "custom":
            image = cfg["image"]
            if not image:
                errors.append(f"{label}: enter a public container image reference.")
            elif " " in image or not IMAGE_RE.match(image):
                errors.append(f"{label}: invalid image reference (public images only; no spaces).")
    return errors
