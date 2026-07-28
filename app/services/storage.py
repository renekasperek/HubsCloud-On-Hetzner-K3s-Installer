from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR, instance_dir
from schemas.models import InstanceSpec, InstanceStatus, VolumeInventory


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_spec(instance_id: str) -> InstanceSpec:
    path = instance_dir(instance_id) / "spec.json"
    return InstanceSpec.model_validate_json(path.read_text())


def save_spec(spec: InstanceSpec) -> None:
    inst = instance_dir(spec.id)
    inst.mkdir(parents=True, exist_ok=True)
    (inst / "spec.json").write_text(spec.model_dump_json(indent=2))


def load_secrets(instance_id: str) -> dict:
    path = instance_dir(instance_id) / "secrets.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_secrets(instance_id: str, secrets: dict) -> None:
    inst = instance_dir(instance_id)
    inst.mkdir(parents=True, exist_ok=True)
    (inst / "secrets.json").write_text(json.dumps(secrets, indent=2))


def load_status(instance_id: str) -> InstanceStatus:
    path = instance_dir(instance_id) / "status.json"
    if not path.exists():
        return InstanceStatus()
    return InstanceStatus.model_validate_json(path.read_text())


def save_status(instance_id: str, status: InstanceStatus) -> None:
    status.updated_at = _now()
    inst = instance_dir(instance_id)
    inst.mkdir(parents=True, exist_ok=True)
    (inst / "status.json").write_text(status.model_dump_json(indent=2))


def append_log(instance_id: str, message: str) -> None:
    inst = instance_dir(instance_id)
    logs_dir = inst / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "pipeline.log"
    line = f"[{_now()}] {message}\n"
    with log_path.open("a") as f:
        f.write(line)


def list_instances() -> list[dict]:
    base = DATA_DIR / "instances"
    if not base.exists():
        return []
    results = []
    for path in sorted(base.iterdir()):
        if not path.is_dir():
            continue
        spec_path = path / "spec.json"
        if not spec_path.exists():
            continue
        spec = InstanceSpec.model_validate_json(spec_path.read_text())
        status = load_status(spec.id)
        results.append(
            {
                "id": spec.id,
                "hub_domain": spec.hub_domain,
                "state": status.state,
                "phase": status.phase,
                "created_at": spec.created_at,
            }
        )
    return results


def save_deployment_info(instance_id: str, info: dict) -> None:
    path = instance_dir(instance_id) / "deployment_info.json"
    path.write_text(json.dumps(info, indent=2))


def load_volumes_inventory(instance_id: str) -> VolumeInventory | None:
    path = instance_dir(instance_id) / "volumes-inventory.json"
    if not path.exists():
        return None
    return VolumeInventory.model_validate_json(path.read_text())


def save_volumes_inventory(instance_id: str, inventory: VolumeInventory) -> None:
    inst = instance_dir(instance_id)
    inst.mkdir(parents=True, exist_ok=True)
    (inst / "volumes-inventory.json").write_text(inventory.model_dump_json(indent=2))
