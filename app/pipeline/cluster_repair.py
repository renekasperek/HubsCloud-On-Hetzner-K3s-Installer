from __future__ import annotations

import shlex

from services.cluster_join import (
    MASTER_PRIVATE_IP,
    classify_node_issue,
    diagnose,
    _ssh_key,
)
from services.ssh import ssh_run
from services.providers.hetzner.api import fetch_cluster_servers, server_public_ip
from services.storage import append_log, load_secrets, load_spec

NETPLAN_PATH = "/etc/netplan/51-hcce-private.yaml"
NETPLAN_CONTENT = """network:
  version: 2
  ethernets:
    enp7s0:
      dhcp4: true
      dhcp4-overrides:
        route-metric: 100
"""

K3S_INSTALL: dict[str, str] = {
    "hcce-master-db": (
        'curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --cluster-init --disable-cloud-controller '
        '--kubelet-arg=cloud-provider=external --disable traefik --flannel-iface=enp7s0 --cluster-cidr=10.42.0.0/16 --service-cidr=10.43.0.0/16 '
        '--tls-san=10.0.1.1 --token={token}" sh -'
    ),
    "hcce-webrtc-worker": (
        'curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --server https://10.0.1.1:6443 '
        '--token={token} --flannel-iface=enp7s0 --node-ip=10.0.1.2 --disable-cloud-controller '
        '--kubelet-arg=cloud-provider=external --disable traefik" sh -'
    ),
    "hcce-web-worker": (
        'curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --server https://10.0.1.1:6443 '
        '--token={token} --flannel-iface=enp7s0 --node-ip=10.0.1.3 --disable-cloud-controller '
        '--kubelet-arg=cloud-provider=external --disable traefik" sh -'
    ),
}


def _repair_private_network(instance_id: str, key, public_ip: str) -> bool:
    append_log(instance_id, f"Repair: bringing up private network on {public_ip}")
    script = (
        "set -e; "
        "ip link set enp7s0 up 2>/dev/null || true; "
        "mkdir -p /etc/netplan; "
        f"printf '%s' {shlex.quote(NETPLAN_CONTENT)} > {NETPLAN_PATH}; "
        "netplan apply 2>/dev/null || true; "
        "sleep 3; "
        f"ping -c1 -W5 {MASTER_PRIVATE_IP} >/dev/null 2>&1"
    )
    for user in ("cluster", "root"):
        prefix = "sudo " if user == "cluster" else ""
        code, _, err = ssh_run(key, public_ip, user, prefix + script, timeout=120)
        if code == 0:
            append_log(instance_id, f"Repair: private network restored on {public_ip}")
            return True
        append_log(instance_id, f"Repair private network {user}@{public_ip}: {err[:200]}")
    return False


def _wait_for_master_k3s(instance_id: str, key, public_ip: str) -> bool:
    append_log(instance_id, f"Repair: waiting for master K3s API before join from {public_ip}")
    script = (
        "set -e; "
        "MASTER=10.0.1.1; "
        "for i in $(seq 1 90); do "
        "if curl -k -sf --connect-timeout 5 --max-time 10 https://${MASTER}:6443/readyz >/dev/null 2>&1; then exit 0; fi; "
        "sleep 10; "
        "done; exit 1"
    )
    for user in ("cluster", "root"):
        prefix = "sudo " if user == "cluster" else ""
        code, _, err = ssh_run(key, public_ip, user, prefix + script, timeout=960)
        if code == 0:
            append_log(instance_id, "Repair: master K3s API is ready")
            return True
        append_log(instance_id, f"Repair wait for master via {user}@{public_ip}: {err[:200]}")
    return False


def _install_k3s(instance_id: str, key, public_ip: str, server_name: str, token: str) -> bool:
    template = K3S_INSTALL.get(server_name)
    if not template:
        return False
    if server_name != "hcce-master-db" and not _wait_for_master_k3s(instance_id, key, public_ip):
        append_log(instance_id, f"Repair: master K3s not ready — skipping join on {server_name}")
        return False
    cmd = template.format(token=token)
    append_log(instance_id, f"Repair: installing k3s on {server_name} ({public_ip})")
    for user in ("cluster", "root"):
        remote = f"sudo bash -c {shlex.quote(cmd)}" if user == "cluster" else f"bash -c {shlex.quote(cmd)}"
        code, _, err = ssh_run(key, public_ip, user, remote, timeout=600)
        if code == 0:
            append_log(instance_id, f"Repair: k3s install finished on {server_name}")
            return True
        append_log(instance_id, f"Repair k3s {user}@{public_ip}: {err[:200]}")
    return False


def repair_node(instance_id: str, server_name: str, issue: str | None, public_ip: str) -> dict:
    key = _ssh_key(instance_id)
    if not key:
        return {"server": server_name, "ok": False, "action": "none", "detail": "SSH key missing"}
    if not public_ip:
        return {"server": server_name, "ok": False, "action": "none", "detail": "No public IP"}

    if issue == "ssh_unreachable":
        append_log(instance_id, f"Repair: cannot reach {server_name} via SSH — check Hetzner console / firewall")
        return {"server": server_name, "ok": False, "action": "ssh_unreachable", "detail": "SSH unreachable"}

    if issue == "ssh_key_mismatch":
        append_log(
            instance_id,
            f"Repair: SSH key rejected on {server_name} — VM may be stale; retry provisioning recreates workers",
        )
        return {"server": server_name, "ok": False, "action": "ssh_key_mismatch", "detail": "SSH key rejected"}

    if issue == "cloud_init_running":
        from services.node_diagnostics import probe_node

        diag = probe_node(key, server_name, public_ip)
        append_log(
            instance_id,
            f"Repair: {server_name} cloud-init in progress — {diag.summary}"
            + (f" (stage={diag.bootstrap_stage})" if diag.bootstrap_stage else ""),
        )
        if diag.fatal:
            return {
                "server": server_name,
                "ok": False,
                "action": diag.fatal,
                "detail": diag.summary,
            }
        return {"server": server_name, "ok": True, "action": "wait", "detail": diag.summary or "cloud-init in progress"}

    if issue == "cloud_init_error":
        from services.node_diagnostics import probe_node

        diag = probe_node(key, server_name, public_ip)
        append_log(instance_id, f"Repair: {server_name} cloud-init failed — {diag.summary}")
        return {
            "server": server_name,
            "ok": False,
            "action": "cloud_init_error",
            "detail": diag.summary or "Cloud-init failed",
        }

    if issue and issue.startswith("failed:"):
        append_log(instance_id, f"Repair: {server_name} bootstrap failed — {issue}")
        return {
            "server": server_name,
            "ok": False,
            "action": issue,
            "detail": issue.replace("failed:", "Bootstrap failed: ").replace("-", " "),
        }

    if issue == "k3s_service_failed":
        from services.node_diagnostics import probe_node

        diag = probe_node(key, server_name, public_ip)
        append_log(instance_id, f"Repair: {server_name} K3s service failed — {diag.summary}")
        return {
            "server": server_name,
            "ok": False,
            "action": "k3s_service_failed",
            "detail": diag.summary or "K3s service failed",
        }

    if issue in ("private_network_down", "hetzner_missing", None):
        if issue != "private_network_down":
            current = classify_node_issue(
                key,
                public_ip,
                is_master=(server_name == "hcce-master-db"),
            )
            if current not in ("private_network_down", "k3s_inactive", "cloud_init_running"):
                if current == "ssh_unreachable":
                    return {"server": server_name, "ok": False, "action": "ssh_unreachable", "detail": "SSH unreachable"}
                if current == "ssh_key_mismatch":
                    return {"server": server_name, "ok": False, "action": "ssh_key_mismatch", "detail": "SSH key rejected"}
        if _repair_private_network(instance_id, key, public_ip):
            issue = classify_node_issue(
                key,
                public_ip,
                is_master=(server_name == "hcce-master-db"),
            )
        else:
            return {"server": server_name, "ok": False, "action": "private_network", "detail": "Could not restore private network"}

    if issue == "k3s_inactive" or issue is None:
        secrets = load_secrets(instance_id)
        token = secrets.get("k3s_token", "")
        if not token:
            return {"server": server_name, "ok": False, "action": "k3s", "detail": "k3s token missing"}
        if _install_k3s(instance_id, key, public_ip, server_name, token):
            return {"server": server_name, "ok": True, "action": "k3s_install", "detail": "k3s installed"}
        return {"server": server_name, "ok": False, "action": "k3s", "detail": "k3s install failed"}

    return {"server": server_name, "ok": True, "action": "noop", "detail": f"No repair needed ({issue})"}


def repair_cluster_join(instance_id: str) -> dict:
    spec = load_spec(instance_id)
    if not spec.hetzner_api_token:
        return {"ok": False, "error": "Hetzner API token required", "results": []}

    join_status = diagnose(instance_id)
    hetzner_servers = fetch_cluster_servers(spec.hetzner_api_token)
    results: list[dict] = []

    targets = [s for s in join_status.servers if not s.k8s_present or s.issue]
    if not targets:
        missing_names = set(join_status.missing)
        targets = [s for s in join_status.servers if s.name in missing_names]

    append_log(instance_id, f"Cluster join repair started for {len(targets)} node(s)")

    for server in targets:
        hc = hetzner_servers.get(server.name, {})
        public_ip = server.public_ip or server_public_ip(hc)
        result = repair_node(instance_id, server.name, server.issue, public_ip)
        results.append(result)

    ok = all(r.get("ok") for r in results) if results else True
    after = diagnose(instance_id)
    from services.node_diagnostics import log_cluster_diagnostics

    diagnostics = log_cluster_diagnostics(instance_id)
    append_log(
        instance_id,
        f"Cluster join repair finished — {after.joined_ready}/{after.expected_nodes} ready",
    )
    if not ok:
        failed = [r for r in results if not r.get("ok")]
        details = "; ".join(f"{r['server']}: {r.get('detail', '?')}" for r in failed)
        append_log(instance_id, f"Repair could not fix: {details}")
    return {
        "ok": ok,
        "results": results,
        "join_status": after.model_dump(),
        "diagnostics": [d.to_dict() for d in diagnostics],
    }
