from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from config import instance_dir
from services.cluster_join import BOOTSTRAP_LOG_FILE, BOOTSTRAP_STAGE_FILE, EXPECTED_NODES, _ssh_key
from services.providers.hetzner.api import fetch_cluster_servers, server_public_ip
from services.ssh import ssh_diagnose, ssh_probe
from services.storage import append_log, load_spec

# How long the same bootstrap stage may persist before we treat it as stuck.
STUCK_STAGE_SECONDS = 900
# Master must expose kubeconfig within this window after terraform apply.
MASTER_KUBECONFIG_TIMEOUT_SECONDS = 900


@dataclass
class NodeDiagnostic:
    name: str
    public_ip: str = ""
    reachable: bool = False
    ssh_issue: str | None = None
    bootstrap_stage: str = ""
    cloud_init_status: str = ""
    k3s_active: str = ""
    k3s_failed: str = ""
    bootstrap_log_tail: str = ""
    cloud_init_output_tail: str = ""
    fatal: str = ""
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_probe_output(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def probe_node(key: Path, name: str, public_ip: str) -> NodeDiagnostic:
    diag = NodeDiagnostic(name=name, public_ip=public_ip)
    if not public_ip:
        diag.fatal = "hetzner_missing"
        diag.summary = "Server has no public IP in Hetzner yet"
        return diag

    reachable, ssh_issue = ssh_diagnose(key, public_ip)
    diag.reachable = reachable
    diag.ssh_issue = ssh_issue
    if not reachable:
        # Only ssh_key_mismatch is terminal — the keys will never work by
        # waiting. Generic ssh_unreachable (timeout / no route / connection
        # refused) is expected while the VM is still booting or cloud-init
        # hasn't started sshd yet; let the outer stuck-stage check decide.
        if ssh_issue == "ssh_key_mismatch":
            diag.fatal = "ssh_key_mismatch"
            diag.summary = "SSH key rejected — regenerate key pair in wizard and recreate VMs"
        else:
            diag.summary = f"SSH unreachable ({ssh_issue or 'ssh_unreachable'}) — VM may still be booting"
        return diag

    remote = (
        f"stage=$(cat {BOOTSTRAP_STAGE_FILE} 2>/dev/null || true); "
        'ci=$(cloud-init status 2>/dev/null | head -1 || echo unknown); '
        'k3s=$(systemctl is-active k3s 2>/dev/null || echo inactive); '
        'k3sf=$(systemctl is-failed k3s 2>/dev/null || echo unknown); '
        f'log=$(sudo tail -40 {BOOTSTRAP_LOG_FILE} 2>/dev/null | tr "\\n" " | " || true); '
        'ciout=$(sudo tail -10 /var/log/cloud-init-output.log 2>/dev/null | tr "\\n" " | " || true); '
        'printf "stage=%s\\nci=%s\\nk3s=%s\\nk3sf=%s\\nlog=%s\\nciout=%s\\n" '
        '"$stage" "$ci" "$k3s" "$k3sf" "$log" "$ciout"'
    )
    ok, out = ssh_probe(key, public_ip, remote)
    if ok:
        fields = _parse_probe_output(out)
        diag.bootstrap_stage = fields.get("stage", "")
        diag.cloud_init_status = fields.get("ci", "")
        diag.k3s_active = fields.get("k3s", "")
        diag.k3s_failed = fields.get("k3sf", "")
        diag.bootstrap_log_tail = fields.get("log", "")[:4000]
        diag.cloud_init_output_tail = fields.get("ciout", "")[:2000]
    else:
        diag.summary = f"Could not read bootstrap state: {out[:200]}"

    _apply_fatal_rules(diag)
    if not diag.summary:
        diag.summary = _default_summary(diag)
    return diag


def _default_summary(diag: NodeDiagnostic) -> str:
    stage = diag.bootstrap_stage or "unknown"
    if diag.k3s_active == "active":
        return "K3s running"
    if "running" in diag.cloud_init_status.lower():
        return f"Cloud-init running (stage: {stage})"
    if stage:
        return f"Bootstrap stage: {stage}"
    return diag.cloud_init_status or "Status unknown"


def _apply_fatal_rules(diag: NodeDiagnostic) -> None:
    if diag.fatal:
        return
    ci = diag.cloud_init_status.lower()
    stage = diag.bootstrap_stage

    # Cloud-init reports "error" when any module (packages/apt/write_files/…)
    # returns non-zero, even if runcmd is still running fine. Treat it as fatal
    # ONLY if our bootstrap script also flagged failure via a "failed:*" stage
    # marker — otherwise the runcmd script may still recover. The stuck-stage
    # timer will still catch a runcmd that truly hangs.
    if "error" in ci and stage.startswith("failed:"):
        diag.fatal = "cloud_init_error"
        diag.summary = f"Cloud-init failed — {diag.cloud_init_output_tail or diag.cloud_init_status}"
        return

    if stage.startswith("failed:"):
        reason = stage.split(":", 1)[-1].replace("-", " ")
        diag.fatal = stage
        diag.summary = f"Bootstrap failed at {reason}"
        return

    if diag.k3s_failed == "failed":
        diag.fatal = "k3s_service_failed"
        diag.summary = "K3s service failed — see cloud-init logs on the node"
        return

    if diag.k3s_active == "failed":
        diag.fatal = "k3s_service_failed"
        diag.summary = "K3s service is in failed state"


def probe_cluster(instance_id: str) -> list[NodeDiagnostic]:
    key = _ssh_key(instance_id)
    if not key:
        return []

    spec = load_spec(instance_id)
    hetzner_servers: dict[str, dict] = {}
    if spec.hetzner_api_token:
        try:
            hetzner_servers = fetch_cluster_servers(spec.hetzner_api_token)
        except Exception:
            hetzner_servers = {}

    results: list[NodeDiagnostic] = []
    for expected in EXPECTED_NODES:
        name = expected["name"]
        hc = hetzner_servers.get(name, {})
        public_ip = server_public_ip(hc) if hc else ""
        results.append(probe_node(key, name, public_ip))
    return results


def format_cluster_report(diagnostics: list[NodeDiagnostic]) -> str:
    lines = ["Cluster bootstrap diagnostics:"]
    for d in diagnostics:
        flag = f" FATAL: {d.summary}" if d.fatal else ""
        lines.append(
            f"  • {d.name} ({d.public_ip or 'no IP'}): {d.summary}{flag}"
        )
        if d.bootstrap_stage:
            lines.append(f"      stage={d.bootstrap_stage}")
        if d.cloud_init_status:
            lines.append(f"      cloud-init={d.cloud_init_status}")
        if d.k3s_active:
            lines.append(f"      k3s={d.k3s_active}")
        if d.bootstrap_log_tail:
            lines.append(f"      log: {d.bootstrap_log_tail}")
    return "\n".join(lines)


def save_diagnostics_snapshot(instance_id: str, diagnostics: list[NodeDiagnostic]) -> Path:
    path = instance_dir(instance_id) / "diagnostics.json"
    path.write_text(json.dumps([d.to_dict() for d in diagnostics], indent=2))
    return path


def log_cluster_diagnostics(instance_id: str, diagnostics: list[NodeDiagnostic] | None = None) -> list[NodeDiagnostic]:
    items = diagnostics or probe_cluster(instance_id)
    append_log(instance_id, format_cluster_report(items))
    save_diagnostics_snapshot(instance_id, items)
    return items


def first_fatal(diagnostics: list[NodeDiagnostic]) -> NodeDiagnostic | None:
    for d in diagnostics:
        if d.fatal:
            return d
    return None


def check_stuck_stage(
    tracker: dict[str, tuple[str, float]],
    name: str,
    stage: str,
    *,
    now: float | None = None,
) -> str | None:
    """Return error message if stage unchanged longer than STUCK_STAGE_SECONDS."""
    if not stage:
        return None
    ts = now or time.time()
    prev_stage, first_seen = tracker.get(name, ("", ts))
    if stage != prev_stage:
        tracker[name] = (stage, ts)
        return None
    if ts - first_seen >= STUCK_STAGE_SECONDS:
        return f"{name} stuck at bootstrap stage '{stage}' for {int(ts - first_seen)}s"
    return None


def pipeline_failure_message(title: str, diagnostics: list[NodeDiagnostic], extra: str = "") -> str:
    fatal = first_fatal(diagnostics)
    report = format_cluster_report(diagnostics)
    parts = [title]
    if fatal:
        parts.append(f"Root cause: {fatal.name} — {fatal.summary}")
    if extra:
        parts.append(extra)
    parts.append(report)
    parts.append("Full snapshot saved to diagnostics.json in the instance data folder.")
    return "\n".join(parts)
