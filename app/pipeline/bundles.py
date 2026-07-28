from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from config import instance_dir
from schemas.models import InstanceSpec
from services.storage import load_secrets, load_spec, load_status


def build_secrets_zip(instance_id: str, *, progress_url: str | None = None) -> bytes:
    spec = load_spec(instance_id)
    secrets = load_secrets(instance_id)
    info_path = instance_dir(instance_id) / "deployment_info.json"
    deployment_info: dict = {}
    if info_path.exists():
        deployment_info = json.loads(info_path.read_text())

    progress = (progress_url or "").strip()
    if not progress:
        progress = f"http://127.0.0.1:8080/instances/{instance_id}"
    setup = progress.rstrip("/") + "/setup" if not progress.rstrip("/").endswith("/setup") else progress

    readme_lines = [
        "Hubs Cloud installer — secrets bundle",
        "=====================================",
        "",
        "Instance ID",
        "-----------",
        instance_id,
        "",
        "Installer UI (bookmark this)",
        "----------------------------",
        f"Progress page: {progress}",
        f"Wizard setup:  {setup}",
        "",
        "After tearing down and rebuilding the installer Docker container, mount the same",
        "./data directory and open the progress URL above to view this cluster again.",
        "",
        "Hub",
        "---",
        f"Domain:    {spec.hub_domain or '—'}",
        f"Admin URL: {deployment_info.get('admin_url') or (f'https://{spec.hub_domain}' if spec.hub_domain else '—')}",
    ]
    lb_ip = deployment_info.get("lb_ip")
    if lb_ip:
        readme_lines.append(f"Load balancer IP: {lb_ip}")
    master_ip = deployment_info.get("master_ip")
    readme_lines.extend(
        [
            "",
            "SSH access",
            "----------",
            "The installer generated an Ed25519 key pair for provisioning and optional node access.",
            "",
            "  ssh/id_ed25519      — private key (keep secret; chmod 600 before use)",
            "  ssh/id_ed25519.pub  — public key installed on all nodes",
            "",
            "Connect as the cluster user (root SSH is disabled after provisioning):",
            "",
            "  chmod 600 ssh/id_ed25519",
            "  ssh -i ssh/id_ed25519 cluster@<node-public-ip>",
            "",
        ]
    )
    if master_ip:
        readme_lines.append(f"Master node IP (example): {master_ip}")
        readme_lines.append("")
    readme_lines.extend(
        [
            "Web and WebRTC worker public IPs are in the Hetzner Cloud Console.",
            "If you applied the hardened firewall without keeping SSH open, port 22 is",
            "closed on public node IPs and direct SSH from the internet will not work.",
            "",
            "",
            "Files in this archive",
            "---------------------",
            "README.txt              — this file",
            "passwords.txt           — generated secrets and SMTP/API credentials",
            "kubeconfig              — kubectl access to the cluster",
            "spec-redacted.json      — installer spec (sensitive fields redacted)",
            "rendered/hcce.yaml      — full HCCE manifest applied to the cluster",
            "rendered/k8s/           — rendered platform manifests (HAProxy, cert-manager, etc.)",
            "volumes-inventory.json  — PVC → Hetzner volume ID mapping for disaster recovery",
            "ssh/id_ed25519          — SSH private key for node access (cluster user)",
            "ssh/id_ed25519.pub      — matching SSH public key",
            "",
        ]
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", "\n".join(readme_lines))
        lines = []
        for k, v in secrets.items():
            lines.append(f"{k}={v}")
        lines.append(f"smtp_password={spec.smtp_password}")
        lines.append(f"hetzner_api_token={spec.hetzner_api_token}")
        if spec.sketchfab_api_key:
            lines.append(f"sketchfab_api_key={spec.sketchfab_api_key}")
        if spec.tenor_api_key:
            lines.append(f"tenor_api_key={spec.tenor_api_key}")
        zf.writestr("passwords.txt", "\n".join(lines) + "\n")
        kc = instance_dir(instance_id) / "kubeconfig"
        if kc.exists():
            zf.write(kc, "kubeconfig")
        redacted = spec.model_dump()
        redacted["hetzner_api_token"] = "***"
        redacted["smtp_password"] = "***"
        redacted["ssh_private_key_pem"] = "***"
        zf.writestr("spec-redacted.json", json.dumps(redacted, indent=2))
        ssh_dir = instance_dir(instance_id) / "ssh"
        priv = ssh_dir / "id_ed25519"
        pub = ssh_dir / "id_ed25519.pub"
        if priv.exists():
            zf.write(priv, "ssh/id_ed25519")
        if pub.exists():
            zf.write(pub, "ssh/id_ed25519.pub")
        rendered = instance_dir(instance_id) / "rendered"
        if rendered.exists():
            for path in sorted(rendered.rglob("*")):
                if path.is_file():
                    arcname = Path("rendered") / path.relative_to(rendered)
                    zf.write(path, arcname.as_posix())
        inv_path = instance_dir(instance_id) / "volumes-inventory.json"
        if inv_path.exists():
            zf.write(inv_path, "volumes-inventory.json")
    return buf.getvalue()


def build_debug_bundle(instance_id: str) -> bytes:
    from services.cluster_join import get_cluster_join_status

    spec = load_spec(instance_id)
    status = load_status(instance_id)
    join_status = get_cluster_join_status(instance_id)

    log_path = instance_dir(instance_id) / "logs" / "pipeline.log"
    log_lines: list[str] = []
    if log_path.exists():
        log_lines = log_path.read_text().splitlines()[-500:]

    redacted = spec.model_dump()
    redacted["hetzner_api_token"] = "***"
    redacted["smtp_password"] = "***"
    redacted["ssh_private_key_pem"] = "***"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", "Hubs installer debug bundle — share with support if provisioning is stuck.\n")
        zf.writestr("status.json", status.model_dump_json(indent=2))
        zf.writestr("spec-redacted.json", json.dumps(redacted, indent=2))
        zf.writestr("cluster-join-status.json", join_status.model_dump_json(indent=2))
        diag_path = instance_dir(instance_id) / "diagnostics.json"
        if diag_path.exists():
            zf.writestr("diagnostics.json", diag_path.read_text())
        zf.writestr("pipeline.log", "\n".join(log_lines) + ("\n" if log_lines else ""))
        kc = instance_dir(instance_id) / "kubeconfig"
        if kc.exists():
            kc_text = kc.read_text()
            kc_text = kc_text.replace("certificate-authority-data:", "certificate-authority-data: [REDACTED]")
            zf.writestr("kubeconfig-redacted.txt", kc_text[:2000] + "\n… truncated …\n")
    return buf.getvalue()
