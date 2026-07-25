from __future__ import annotations

import time

from config import instance_dir
from pipeline.core import PipelineError, kube_env, run_cmd
from services.storage import append_log


def install_ccm_csi(instance_id: str, spec) -> None:
    k8s = instance_dir(instance_id) / "rendered" / "k8s"
    env = kube_env(instance_id)
    run_cmd(["kubectl", "apply", "-f", str(k8s / "ccm" / "secret.yaml")], env=env)
    run_cmd(
        [
            "kubectl",
            "apply",
            "-f",
            "https://github.com/hetznercloud/hcloud-cloud-controller-manager/releases/download/v1.23.0/ccm-networks.yaml",
        ],
        env=env,
    )
    run_cmd(["kubectl", "apply", "-f", str(k8s / "csi" / "secret.yaml")], env=env)
    run_cmd(["helm", "repo", "add", "hcloud", "https://charts.hetzner.cloud"], env=env)
    run_cmd(["helm", "repo", "update"], env=env)
    run_cmd(
        [
            "helm",
            "upgrade",
            "--install",
            "hcloud-csi",
            "hcloud/hcloud-csi",
            "-n",
            "kube-system",
            "--set",
            "controller.hcloudToken.secret.name=hcloud-csi",
            "--set",
            "controller.hcloudToken.secret.key=token",
        ],
        env=env,
        timeout=600,
    )
    run_cmd(["kubectl", "apply", "-f", str(k8s / "csi" / "storageclass.yaml")], env=env)
    run_cmd(["kubectl", "apply", "-f", str(k8s / "metrics-server")], env=env)


def install_cert_manager(instance_id: str) -> None:
    env = kube_env(instance_id)
    run_cmd(["helm", "repo", "add", "jetstack", "https://charts.jetstack.io"], env=env)
    run_cmd(["helm", "repo", "update"], env=env)
    run_cmd(
        [
            "helm",
            "upgrade",
            "--install",
            "cert-manager",
            "jetstack/cert-manager",
            "--namespace",
            "cert-manager",
            "--create-namespace",
            "--set",
            "crds.enabled=true",
        ],
        env=env,
        timeout=600,
    )
    for _ in range(60):
        result = run_cmd(
            ["kubectl", "get", "pods", "-n", "cert-manager", "-o", "json"],
            env=env,
        )
        if result.returncode == 0:
            import json

            pods = json.loads(result.stdout).get("items", [])
            if pods and all(p.get("status", {}).get("phase") == "Running" for p in pods):
                return
        time.sleep(5)
    raise PipelineError("cert-manager pods not ready")


def kubectl_apply_dir(instance_id: str, path) -> None:
    env = kube_env(instance_id)
    for f in sorted(path.glob("*.yaml")):
        run_cmd(["kubectl", "apply", "-f", str(f)], env=env)
