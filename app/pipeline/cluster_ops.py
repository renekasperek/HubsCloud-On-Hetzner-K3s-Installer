from __future__ import annotations

import shlex
import time

from config import instance_dir
from pipeline.core import PipelineError, kube_env, run_cmd, update_status
from pipeline.terraform_ops import terraform_output
from services.node_diagnostics import (
    MASTER_KUBECONFIG_TIMEOUT_SECONDS,
    check_stuck_stage,
    first_fatal,
    log_cluster_diagnostics,
    pipeline_failure_message,
    probe_node,
)
from services.ssh import ssh_args, ssh_auth_ok, ssh_cat_file, ssh_err_snippet
from services.storage import append_log


def fetch_kubeconfig(instance_id: str, master_ip: str) -> None:
    inst = instance_dir(instance_id)
    key = inst / "ssh" / "id_ed25519"
    if not key.exists():
        raise PipelineError("SSH private key missing — regenerate the SSH key in the wizard")
    key.chmod(0o600)
    kube_dest = inst / "kubeconfig"

    remote_paths = [
        "/home/cluster/.kube/config",
        "/etc/rancher/k3s/k3s.yaml",
    ]
    users = ["cluster", "root"]

    deadline = time.time() + MASTER_KUBECONFIG_TIMEOUT_SECONDS
    last_report_at = 0.0
    stage_tracker: dict[str, tuple[str, float]] = {}
    master_name = "hcce-master-db"

    while time.time() < deadline:
        for user in users:
            ok, err_msg = ssh_auth_ok(key, master_ip, user)
            if not ok:
                continue
            for remote_path in remote_paths:
                ok, content, err = ssh_cat_file(key, master_ip, user, remote_path)
                if ok:
                    kc = content.replace("127.0.0.1", master_ip).replace("localhost", master_ip)
                    kube_dest.write_text(kc)
                    append_log(instance_id, f"Fetched kubeconfig from {user}@{master_ip}:{remote_path}")
                    return

        now = time.time()
        if now - last_report_at >= 60:
            last_report_at = now
            diag = probe_node(key, master_name, master_ip)
            append_log(
                instance_id,
                f"[{master_name}] {diag.summary}"
                + (f" | cloud-init: {diag.cloud_init_status}" if diag.cloud_init_status else "")
                + (f" | k3s: {diag.k3s_active}" if diag.k3s_active else ""),
            )
            if diag.fatal:
                diagnostics = log_cluster_diagnostics(instance_id)
                raise PipelineError(
                    pipeline_failure_message(
                        "Master node bootstrap failed before K3s kubeconfig was available.",
                        diagnostics,
                    )
                )
            stuck = check_stuck_stage(stage_tracker, master_name, diag.bootstrap_stage, now=now)
            if stuck:
                diagnostics = log_cluster_diagnostics(instance_id)
                raise PipelineError(
                    pipeline_failure_message(
                        f"Master bootstrap appears stuck: {stuck}",
                        diagnostics,
                        "Retry provisioning recreates the VMs with fresh cloud-init.",
                    )
                )

        time.sleep(20)

    diagnostics = log_cluster_diagnostics(instance_id)
    raise PipelineError(
        pipeline_failure_message(
            f"Timed out after {MASTER_KUBECONFIG_TIMEOUT_SECONDS // 60} minutes waiting for master K3s kubeconfig.",
            diagnostics,
            "If SSH key mismatch is reported, regenerate the key pair and reprovision.",
        )
    )


def wait_nodes_ready(instance_id: str, timeout: int = 1200) -> None:
    import json

    from pipeline.cluster_repair import repair_cluster_join
    from services.cluster_join import diagnose
    from services.node_diagnostics import check_stuck_stage, first_fatal, log_cluster_diagnostics
    from services.storage import load_spec

    spec = load_spec(instance_id)
    deadline = time.time() + timeout
    last_logged = 0.0
    last_diagnose = 0.0
    auto_repair_attempted = False
    stage_tracker: dict[str, tuple[str, float]] = {}
    expected = 3

    while time.time() < deadline:
        result = run_cmd(["kubectl", "get", "nodes", "-o", "json"], env=kube_env(instance_id))
        if result.returncode == 0:
            data = json.loads(result.stdout)
            items = data.get("items", [])
            ready = sum(
                1
                for n in items
                if any(
                    c.get("type") == "Ready" and c.get("status") == "True"
                    for c in n.get("status", {}).get("conditions", [])
                )
            )
            if time.time() - last_logged >= 30:
                names = [n.get("metadata", {}).get("name", "?") for n in items]
                append_log(
                    instance_id,
                    f"Waiting for {expected} Ready nodes ({ready}/{expected} ready, {len(items)} registered: {', '.join(names) or 'none'})",
                )
                last_logged = time.time()

            if len(items) >= expected and ready >= expected:
                return

        if time.time() - last_diagnose >= 60:
            last_diagnose = time.time()
            diagnostics = log_cluster_diagnostics(instance_id)
            fatal = first_fatal(diagnostics)
            if fatal:
                raise PipelineError(
                    pipeline_failure_message(
                        "Cluster join failed during node bootstrap.",
                        diagnostics,
                    )
                )
            now = time.time()
            for d in diagnostics:
                stuck = check_stuck_stage(stage_tracker, d.name, d.bootstrap_stage, now=now)
                if stuck:
                    raise PipelineError(
                        pipeline_failure_message(
                            f"Node bootstrap appears stuck: {stuck}",
                            diagnostics,
                            "Use Retry provisioning on the progress page to recreate worker VMs.",
                        )
                    )

            join_status = diagnose(instance_id)
            if join_status.missing and join_status.stuck_seconds >= 600:
                missing_list = ", ".join(join_status.missing)
                append_log(
                    instance_id,
                    f"Cluster join stalled {join_status.stuck_seconds}s — missing: {missing_list}",
                )
                if spec.auto_repair_cluster_join and not auto_repair_attempted:
                    auto_repair_attempted = True
                    append_log(instance_id, "Attempting automatic cluster join repair")
                    try:
                        repair_cluster_join(instance_id)
                    except Exception as e:
                        append_log(instance_id, f"Automatic cluster join repair failed: {e}")

        time.sleep(15)

    diagnostics = log_cluster_diagnostics(instance_id)
    missing = ", ".join(d.name for d in diagnostics if d.k3s_active != "active") or "see diagnostics"
    raise PipelineError(
        pipeline_failure_message(
            f"Timed out waiting for all {expected} nodes to become Ready — problem nodes: {missing}",
            diagnostics,
            "Try automatic repair from the progress page, or retry provisioning to recreate workers.",
        )
    )


def harden_ssh_on_nodes(instance_id: str, key, ips: list[str]) -> None:
    harden_cmd = (
        "mkdir -p /etc/ssh/sshd_config.d && "
        "printf '%s\\n' 'PermitRootLogin no' 'PasswordAuthentication no' "
        "'KbdInteractiveAuthentication no' 'AllowUsers cluster' "
        "> /etc/ssh/sshd_config.d/99-hcce-hardening.conf && "
        "systemctl reload ssh"
    )
    quoted = shlex.quote(harden_cmd)
    for ip in ips:
        if not ip:
            continue
        for user in ("cluster", "root"):
            ok, _ = ssh_auth_ok(key, ip, user)
            if not ok:
                continue
            remote = f"sudo bash -c {quoted}" if user == "cluster" else f"bash -c {quoted}"
            result = run_cmd(
                ["ssh", *ssh_args(key), f"{user}@{ip}", remote],
                timeout=60,
            )
            if result.returncode == 0:
                append_log(instance_id, f"SSH hardened on {ip} via {user}")
                break
            append_log(instance_id, f"SSH harden {user}@{ip}: {ssh_err_snippet(result)}")


def harden_cluster_ssh(instance_id: str, master_ip: str) -> None:
    key = instance_dir(instance_id) / "ssh" / "id_ed25519"
    if not key.exists():
        return
    worker_ips = [
        terraform_output(instance_id, name)
        for name in ("webrtc_worker_ip", "web_worker_ip")
    ]
    harden_ssh_on_nodes(instance_id, key, [master_ip, *worker_ips])
