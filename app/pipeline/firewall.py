from __future__ import annotations

from config import instance_dir
from pipeline.core import PipelineError, run_cmd, update_status
from pipeline.errors import format_terraform_error
from renderers import render_terraform
from schemas.models import InstanceSpec
from services.storage import append_log, load_secrets, load_spec, load_status, save_spec


def harden_firewall(instance_id: str, allow_ssh: bool) -> None:
    status = load_status(instance_id)
    if status.state != "succeeded" and status.phase != "firewall":
        raise PipelineError("Cluster must finish provisioning before firewall hardening")
    spec = load_spec(instance_id)
    if spec.firewall_hardened:
        raise PipelineError("Firewall is already hardened")

    spec.firewall_allow_ssh = allow_ssh
    save_spec(spec)

    tf_dir = instance_dir(instance_id) / "terraform"
    if not tf_dir.exists():
        raise PipelineError("Terraform state missing — cannot harden firewall")

    update_status(instance_id, "firewall", 11, "running", "Applying hardened Hetzner firewall rules")
    append_log(instance_id, f"Firewall hardening: allow_ssh={allow_ssh}")

    try:
        secrets = load_secrets(instance_id)
        render_terraform(spec, secrets, firewall_hardened=True, firewall_allow_ssh=allow_ssh)
        result = run_cmd(
            ["terraform", "apply", "-auto-approve", "-input=false", "-no-color"],
            cwd=tf_dir,
            timeout=600,
        )
        append_log(instance_id, result.stdout)
        if result.returncode != 0:
            append_log(instance_id, result.stderr)
            err = format_terraform_error(result.stderr, result.stdout)
            update_status(instance_id, "firewall", 11, "failed", "Firewall hardening failed", error=err, intervention="firewall")
            raise PipelineError(err)

        spec.firewall_hardened = True
        save_spec(spec)
        ssh_note = "SSH port 22 remains open on node public IPs." if allow_ssh else "SSH port 22 is closed on node public IPs."
        update_status(instance_id, "done", 10, "succeeded", f"Provisioning complete — hardened firewall applied. {ssh_note}")
    except PipelineError:
        raise
    except Exception as e:
        err_msg = str(e).strip() or "Firewall hardening failed"
        update_status(instance_id, "firewall", 11, "failed", "Firewall hardening failed", error=err_msg, intervention="firewall")
        raise PipelineError(err_msg) from e
