from __future__ import annotations

import subprocess
from pathlib import Path

from config import instance_dir
from schemas.models import InstanceStatus
from pipeline.errors import classify_pipeline_error
from services.storage import append_log, save_status


class PipelineError(Exception):
    pass


def run_cmd(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    timeout: int = 3600,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise PipelineError(f"Command timed out after {timeout}s: {' '.join(cmd)}") from e


def kube_env(instance_id: str) -> dict:
    import os

    env = os.environ.copy()
    env["KUBECONFIG"] = str(instance_dir(instance_id) / "kubeconfig")
    return env


def update_status(
    instance_id: str,
    phase: str,
    step: int,
    state: str,
    message: str,
    error: str | None = None,
    intervention: str | None = None,
) -> None:
    save_status(
        instance_id,
        InstanceStatus(
            phase=phase,
            step=step,
            state=state,
            message=message,
            error=error,
            intervention=intervention,
        ),
    )
    append_log(instance_id, f"[{phase} step {step}] {message}" + (f" ERROR: {error}" if error else ""))


def mark_pipeline_failed(
    instance_id: str,
    error: str,
    *,
    phase: str | None = None,
    step: int | None = None,
    message: str | None = None,
) -> None:
    from services.storage import load_status

    status = load_status(instance_id)
    if status.state in ("failed", "succeeded"):
        return
    err = error.strip() or "Provisioning failed"
    intervention = classify_pipeline_error(err)
    update_status(
        instance_id,
        phase or status.phase or "validate",
        step if step is not None else (status.step or 1),
        "failed",
        message or status.message or "Provisioning failed",
        err,
        intervention=intervention,
    )
