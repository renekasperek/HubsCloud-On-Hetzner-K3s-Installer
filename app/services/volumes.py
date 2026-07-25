from __future__ import annotations

import re

VOLUME_GI_RE = re.compile(r"^(\d+)Gi$")

# Hetzner Cloud volumes minimum size is 10 GB.
PGSQL_RETICULUM_VOLUME_GB = (10, 20, 50, 100, 200, 500)
PGSQL_BACKUP_VOLUME_GB = (10, 20)

DEFAULT_PGSQL_VOLUME = "10Gi"
DEFAULT_RETICULUM_VOLUME = "10Gi"
DEFAULT_PGSQL_BACKUP_VOLUME = "10Gi"


def gb_to_gi(gb: int) -> str:
    return f"{gb}Gi"


def parse_volume_gb(value: str) -> int | None:
    m = VOLUME_GI_RE.match(value.strip())
    if not m:
        return None
    return int(m.group(1))


def normalize_data_volume(value: str | None, *, default: str = DEFAULT_PGSQL_VOLUME) -> str:
    gb = parse_volume_gb(value or "")
    if gb is None or gb not in PGSQL_RETICULUM_VOLUME_GB:
        return default
    return gb_to_gi(gb)


def normalize_backup_volume(value: str | None, *, default: str = DEFAULT_PGSQL_BACKUP_VOLUME) -> str:
    gb = parse_volume_gb(value or "")
    if gb is None or gb not in PGSQL_BACKUP_VOLUME_GB:
        return default
    return gb_to_gi(gb)


def validate_volume_sizes(
    pgsql: str,
    reticulum: str,
    backup: str,
) -> list[str]:
    errors: list[str] = []
    pgsql_gb = parse_volume_gb(pgsql)
    ret_gb = parse_volume_gb(reticulum)
    backup_gb = parse_volume_gb(backup)

    if pgsql_gb is None or pgsql_gb not in PGSQL_RETICULUM_VOLUME_GB:
        allowed = ", ".join(f"{gb} GB" for gb in PGSQL_RETICULUM_VOLUME_GB)
        errors.append(f"PostgreSQL volume must be one of: {allowed}")
    elif pgsql_gb < 10:
        errors.append("PostgreSQL volume must be at least 10 GB")

    if ret_gb is None or ret_gb not in PGSQL_RETICULUM_VOLUME_GB:
        allowed = ", ".join(f"{gb} GB" for gb in PGSQL_RETICULUM_VOLUME_GB)
        errors.append(f"Reticulum volume must be one of: {allowed}")
    elif ret_gb < 10:
        errors.append("Reticulum volume must be at least 10 GB")

    if backup_gb is None or backup_gb not in PGSQL_BACKUP_VOLUME_GB:
        errors.append("PostgreSQL backup volume must be 10 GB or 20 GB")

    return errors
