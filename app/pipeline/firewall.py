from __future__ import annotations

import json
import re
from pathlib import Path

from config import instance_dir
from pipeline.core import PipelineError, run_cmd, update_status
from pipeline.errors import format_terraform_error
from services.storage import append_log, load_spec, load_status, save_spec


def _set_tfvar(tfvars: Path, name: str, value: str) -> None:
    """Rewrite a single variable in an already-rendered terraform.tfvars.

    Firewall hardening must never re-render the Terraform spec. The rendered
    spec in the instance folder describes the cluster that is actually
    deployed; regenerating it from templates/ would pull in every template
    change made since provisioning. Because user_data, location, image and
    ssh_keys are ForceNew on hcloud_server, that turns "change one firewall
    rule" into "destroy and recreate all three servers".
    """
    text = tfvars.read_text()
    pattern = re.compile(rf"^(\s*{re.escape(name)}\s*=\s*).*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(rf"\g<1>{value}", text, count=1)
    else:
        text = text.rstrip("\n") + f"\n{name} = {value}\n"
    tfvars.write_text(text)


# Hardening is applied with -target so Terraform only ever considers the firewall.
# Servers depend on the firewall, not the other way round, so targeting it never
# pulls them into the plan — which means hardening works regardless of unrelated
# drift elsewhere in the spec (e.g. hcloud_server.location, which the provider
# never writes back into state and which would otherwise force a full rebuild).
FIREWALL_TARGET = "hcloud_firewall.open_firewall"


def _unexpected_changes(tf_dir: Path, plan_file: Path) -> list[str]:
    """Return anything in the plan that is not an in-place firewall rule update.

    Even under -target the plan is verified before it is applied: the only change
    we ever accept is an update to the firewall itself. A *replacement* of the
    firewall is rejected too — the new firewall would get a new ID, and because
    the servers are outside the target they would keep pointing at the old one.
    """
    result = run_cmd(["terraform", "show", "-json", str(plan_file)], cwd=tf_dir, timeout=120)
    if result.returncode != 0:
        raise PipelineError(
            "Could not inspect the firewall plan: "
            + (result.stderr or result.stdout or "terraform show failed").strip()[:300]
        )
    try:
        plan = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise PipelineError(f"Could not parse the firewall plan: {e}") from e

    problems = []
    for change in plan.get("resource_changes", []):
        actions = [a for a in change.get("change", {}).get("actions", []) if a != "no-op"]
        if not actions:
            continue
        address = change.get("address", "?")
        if change.get("type") != "hcloud_firewall":
            problems.append(f"{address} ({'/'.join(actions)})")
        elif actions != ["update"]:
            problems.append(f"{address} ({'/'.join(actions)} — firewall must update in place)")
    return problems


def harden_firewall(instance_id: str, allow_ssh: bool) -> None:
    status = load_status(instance_id)
    if status.state != "succeeded" and status.phase != "firewall":
        raise PipelineError("Cluster must finish provisioning before firewall hardening")
    spec = load_spec(instance_id)
    if spec.firewall_hardened:
        raise PipelineError("Firewall is already hardened")

    tf_dir = instance_dir(instance_id) / "terraform"
    tfvars = tf_dir / "terraform.tfvars"
    if not tf_dir.exists() or not tfvars.exists():
        raise PipelineError("Terraform state missing — cannot harden firewall")

    update_status(instance_id, "firewall", 11, "running", "Applying hardened Hetzner firewall rules")
    append_log(instance_id, f"Firewall hardening: allow_ssh={allow_ssh}")

    plan_file = tf_dir / "firewall.tfplan"
    previous = tfvars.read_text()

    try:
        # Flip only the firewall variables in the deployed spec.
        _set_tfvar(tfvars, "firewall_hardened", "true")
        _set_tfvar(tfvars, "firewall_allow_ssh", "true" if allow_ssh else "false")

        plan = run_cmd(
            [
                "terraform",
                "plan",
                "-input=false",
                "-no-color",
                f"-target={FIREWALL_TARGET}",
                "-out",
                str(plan_file),
            ],
            cwd=tf_dir,
            timeout=600,
        )
        append_log(instance_id, plan.stdout)
        if plan.returncode != 0:
            append_log(instance_id, plan.stderr)
            err = format_terraform_error(plan.stderr, plan.stdout)
            update_status(instance_id, "firewall", 11, "failed", "Firewall hardening failed", error=err, intervention="firewall")
            raise PipelineError(err)

        # Belt and braces: the plan is targeted, but verify it before applying.
        problems = _unexpected_changes(tf_dir, plan_file)
        if problems:
            err = (
                "Firewall hardening aborted — the plan contains changes that are not "
                f"an in-place firewall update: {', '.join(problems)}. "
                "Hardening must only change firewall rules. No changes were applied."
            )
            append_log(instance_id, err)
            update_status(instance_id, "firewall", 11, "failed", "Firewall hardening aborted", error=err, intervention="firewall")
            raise PipelineError(err)

        # Apply the exact plan that was inspected.
        result = run_cmd(
            ["terraform", "apply", "-input=false", "-no-color", str(plan_file)],
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
        spec.firewall_allow_ssh = allow_ssh
        save_spec(spec)
        ssh_note = "SSH port 22 remains open on node public IPs." if allow_ssh else "SSH port 22 is closed on node public IPs."
        update_status(instance_id, "done", 10, "succeeded", f"Provisioning complete — hardened firewall applied. {ssh_note}")
    except PipelineError:
        tfvars.write_text(previous)
        raise
    except Exception as e:
        tfvars.write_text(previous)
        err_msg = str(e).strip() or "Firewall hardening failed"
        update_status(instance_id, "firewall", 11, "failed", "Firewall hardening failed", error=err_msg, intervention="firewall")
        raise PipelineError(err_msg) from e
    finally:
        plan_file.unlink(missing_ok=True)
