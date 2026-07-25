from __future__ import annotations

from pathlib import Path

from config import instance_dir
from pipeline.core import PipelineError, mark_pipeline_failed, run_cmd, update_status
from pipeline.errors import format_terraform_error
from services.storage import append_log


def terraform_step(instance_id: str, cmd: list[str], cwd: Path, label: str, timeout: int = 600) -> None:
    try:
        result = run_cmd(cmd, cwd=cwd, timeout=timeout)
    except PipelineError as e:
        mark_pipeline_failed(instance_id, str(e), phase="terraform", step=3, message=f"Terraform {label} failed")
        raise
    append_log(instance_id, result.stdout)
    if result.returncode != 0:
        append_log(instance_id, result.stderr)
        err = format_terraform_error(result.stderr, result.stdout)
        mark_pipeline_failed(instance_id, err, phase="terraform", step=3, message=f"Terraform {label} failed")
        raise PipelineError(err)


def terraform_output(instance_id: str, name: str) -> str:
    tf_dir = instance_dir(instance_id) / "terraform"
    result = run_cmd(["terraform", "output", "-raw", name], cwd=tf_dir)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        hint = ""
        if "not found" in err.lower() or "no outputs" in err.lower():
            hint = " (Terraform apply may not have finished — delete resources in Hetzner Console and Create cluster again; stale state is cleared automatically.)"
        raise PipelineError(f"terraform output {name} failed: {err}{hint}")
    return result.stdout.strip()
