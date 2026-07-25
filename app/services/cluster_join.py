from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from config import instance_dir
from pipeline.core import kube_env
from schemas.models import ClusterJoinServer, ClusterJoinStatus
from services.providers.hetzner.api import fetch_cluster_servers, server_private_ip, server_public_ip
from services.ssh import ssh_diagnose, ssh_probe, ssh_run
from services.storage import load_spec, load_status

EXPECTED_NODES: list[dict[str, str]] = [
    {"name": "hcce-master-db", "role": "master", "private_ip": "10.0.1.1"},
    {"name": "hcce-webrtc-worker", "role": "webrtc", "private_ip": "10.0.1.2"},
    {"name": "hcce-web-worker", "role": "web", "private_ip": "10.0.1.3"},
]
MASTER_PRIVATE_IP = "10.0.1.1"
CLUSTER_JOIN_REPAIR_AFTER_SECONDS = 600


def mark_cluster_wait_started(instance_id: str) -> None:
    path = instance_dir(instance_id) / "cluster_wait_started"
    path.write_text(str(time.time()))


def recreate_workers_marker(instance_id: str) -> Path:
    return instance_dir(instance_id) / "recreate_workers_on_apply"


def mark_recreate_workers_on_apply(instance_id: str) -> None:
    recreate_workers_marker(instance_id).write_text("1")


def consume_recreate_workers_marker(instance_id: str) -> bool:
    path = recreate_workers_marker(instance_id)
    if path.exists():
        path.unlink()
        return True
    return False


def cluster_wait_started_at(instance_id: str) -> float | None:
    path = instance_dir(instance_id) / "cluster_wait_started"
    if not path.exists():
        return None
    try:
        return float(path.read_text().strip())
    except ValueError:
        return None


def _ssh_key(instance_id: str) -> Path | None:
    key = instance_dir(instance_id) / "ssh" / "id_ed25519"
    return key if key.exists() else None


def ssh_reachable(key: Path, host: str) -> bool:
    ok, _ = ssh_diagnose(key, host)
    return ok


def classify_node_issue(
    key: Path,
    public_ip: str,
    *,
    master_private_ip: str = MASTER_PRIVATE_IP,
    is_master: bool = False,
) -> str | None:
    if not public_ip:
        return "hetzner_missing"
    reachable, ssh_issue = ssh_diagnose(key, public_ip)
    if not reachable:
        return ssh_issue or "ssh_unreachable"

    ok, link_out = ssh_probe(key, public_ip, "ip link show enp7s0 2>/dev/null || true")
    if ok and "state down" in link_out.lower():
        return "private_network_down"

    ok, addr_out = ssh_probe(
        key,
        public_ip,
        "ip -4 -o addr show dev enp7s0 2>/dev/null | awk '{print $4}' | head -1",
    )
    has_private = ok and addr_out and not addr_out.startswith("127.")

    if not has_private:
        return "private_network_down"

    if not is_master:
        ok, ping_out = ssh_probe(
            key,
            public_ip,
            f"ping -c1 -W3 {master_private_ip} >/dev/null 2>&1 && echo ok || echo fail",
        )
        if not ok or ping_out != "ok":
            return "private_network_down"

    ok, ci_out = ssh_probe(key, public_ip, "cloud-init status 2>/dev/null || echo unknown")
    if ok and "running" in ci_out.lower():
        return "cloud_init_running"

    ok, k3s_out = ssh_probe(key, public_ip, "systemctl is-active k3s 2>/dev/null || echo inactive")
    if ok and k3s_out.strip() != "active":
        return "k3s_inactive"

    return None


def _k8s_nodes(instance_id: str) -> dict[str, bool]:
    kc = instance_dir(instance_id) / "kubeconfig"
    if not kc.exists():
        return {}
    result = subprocess.run(
        ["kubectl", "get", "nodes", "-o", "json"],
        env=kube_env(instance_id),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        return {}
    data = json.loads(result.stdout)
    out: dict[str, bool] = {}
    for n in data.get("items", []):
        name = n.get("metadata", {}).get("name", "")
        ready = any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in n.get("status", {}).get("conditions", [])
        )
        if name:
            out[name] = ready
    return out


def _match_k8s_node(server_name: str, k8s_nodes: dict[str, bool]) -> tuple[bool, bool]:
    if server_name in k8s_nodes:
        return True, k8s_nodes[server_name]
    for node_name, ready in k8s_nodes.items():
        if server_name in node_name or node_name in server_name:
            return True, ready
    return False, False


def get_cluster_join_status(instance_id: str) -> ClusterJoinStatus:
    spec = load_spec(instance_id)
    status = load_status(instance_id)
    k8s_nodes = _k8s_nodes(instance_id)
    key = _ssh_key(instance_id)

    hetzner_servers: dict[str, dict] = {}
    hetzner_error: str | None = None
    if spec.hetzner_api_token:
        try:
            hetzner_servers = fetch_cluster_servers(spec.hetzner_api_token)
        except Exception as e:
            hetzner_error = str(e)

    servers: list[ClusterJoinServer] = []
    missing: list[str] = []
    joined_ready = 0
    joined_not_ready = 0

    for expected in EXPECTED_NODES:
        name = expected["name"]
        hc = hetzner_servers.get(name, {})
        public_ip = server_public_ip(hc) if hc else ""
        private_ip = server_private_ip(hc) if hc else expected["private_ip"]
        hetzner_status = hc.get("status", "") if hc else "missing"
        k8s_present, k8s_ready = _match_k8s_node(name, k8s_nodes)

        issue: str | None = None
        is_master = name == "hcce-master-db"
        if not k8s_present and key and public_ip:
            issue = classify_node_issue(key, public_ip, is_master=is_master)
        elif not k8s_present and not hc:
            issue = "hetzner_missing"
        elif not k8s_present:
            issue = "k3s_inactive"

        if k8s_present:
            if k8s_ready:
                joined_ready += 1
            else:
                joined_not_ready += 1
        else:
            missing.append(name)

        servers.append(
            ClusterJoinServer(
                name=name,
                role=expected["role"],
                public_ip=public_ip,
                private_ip=private_ip,
                hetzner_status=hetzner_status,
                k8s_ready=k8s_ready,
                k8s_present=k8s_present,
                issue=issue,
            )
        )

    started = cluster_wait_started_at(instance_id)
    stuck_seconds = int(time.time() - started) if started else 0

    suggested_action = "none"
    if missing or joined_not_ready > 0:
        if stuck_seconds >= CLUSTER_JOIN_REPAIR_AFTER_SECONDS:
            suggested_action = "repair"
        else:
            suggested_action = "wait"

    if status.state == "succeeded" and not missing and joined_not_ready == 0:
        suggested_action = "none"

    return ClusterJoinStatus(
        expected_nodes=len(EXPECTED_NODES),
        joined_ready=joined_ready,
        joined_not_ready=joined_not_ready,
        missing=missing,
        stuck_seconds=max(0, stuck_seconds),
        servers=servers,
        suggested_action=suggested_action,
        error=hetzner_error,
    )


def diagnose(instance_id: str) -> ClusterJoinStatus:
    return get_cluster_join_status(instance_id)
