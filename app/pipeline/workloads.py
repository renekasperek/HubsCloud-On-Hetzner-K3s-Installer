from __future__ import annotations

import time

from config import instance_dir
from pipeline.core import PipelineError, kube_env, run_cmd
from services.storage import append_log


UNINITIALIZED_TAINT = "node.cloudprovider.kubernetes.io/uninitialized"


def wait_nodes_initialized(instance_id: str, timeout: int = 600) -> None:
    """Block until the CCM has set spec.providerID on every node.

    Nodes run kubelet with --cloud-provider=external, so they register carrying
    the uninitialized taint and nothing schedules until the CCM clears it. That
    same providerID (hcloud://<server-id>) is what lets the CCM attach nodes as
    Load Balancer targets — without it the LB is created with zero targets and
    has to be attached by hand in the Hetzner console.

    If the CCM cannot initialize the nodes we must fail loudly here rather than
    let every later step hang on unschedulable pods.
    """
    import json

    env = kube_env(instance_id)
    deadline = time.time() + timeout
    last_missing: list[str] = []

    while time.time() < deadline:
        result = run_cmd(["kubectl", "get", "nodes", "-o", "json"], env=env)
        if result.returncode == 0:
            items = json.loads(result.stdout).get("items", [])
            last_missing = [
                n.get("metadata", {}).get("name", "?")
                for n in items
                if not (n.get("spec", {}).get("providerID") or "").startswith("hcloud://")
            ]
            if items and not last_missing:
                append_log(
                    instance_id,
                    f"CCM initialized all {len(items)} nodes (providerID set) — "
                    "Load Balancer targets will attach automatically",
                )
                return
        time.sleep(10)

    raise PipelineError(
        "Hetzner CCM did not initialize "
        f"{', '.join(last_missing) or 'the nodes'} within {timeout // 60} minutes "
        f"(spec.providerID still unset, {UNINITIALIZED_TAINT} taint still present).\n"
        "Nodes run with --kubelet-arg=cloud-provider=external, so workloads cannot "
        "schedule until the CCM clears that taint, and the ingress Load Balancer "
        "will be created with no targets.\n"
        "Check the API token and network ID in the hcloud secret, then:\n"
        "  kubectl -n kube-system logs deploy/hcloud-cloud-controller-manager"
    )


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
    # Everything after this point needs schedulable nodes.
    wait_nodes_initialized(instance_id)
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
