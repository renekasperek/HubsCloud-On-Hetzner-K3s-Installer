"""Pipeline orchestration — thin re-export layer for API routes."""

from pipeline.bundles import build_debug_bundle, build_secrets_zip
from pipeline.cluster_ops import fetch_kubeconfig, harden_cluster_ssh, wait_nodes_ready
from pipeline.core import PipelineError, mark_pipeline_failed
from pipeline.deployment import (
    build_deployment_info,
    get_ingress_load_balancer_info,
    refresh_deployment_lb_ip,
)
from pipeline.destroy import destroy_cluster
from pipeline.firewall import harden_firewall
from pipeline.k8s_snapshot import get_resources
from pipeline.provision import run_pipeline
from pipeline.spec_validation import validate_hetzner_token, validate_spec
from services.health import evaluate_health
from services.storage import load_spec, load_status
from services.volume_inventory import build_volumes_context, sync_from_cluster


def get_volumes_context(instance_id: str) -> dict:
    spec = load_spec(instance_id)
    return build_volumes_context(spec).model_dump()


def sync_volume_inventory(instance_id: str) -> dict:
    spec = load_spec(instance_id)
    sync_from_cluster(instance_id, spec)
    return build_volumes_context(spec).model_dump()


def get_health(instance_id: str, *, probe_public: bool = True) -> dict:
    import json

    from config import instance_dir

    spec = load_spec(instance_id)
    status = load_status(instance_id)
    snapshot = get_resources(instance_id)
    info_path = instance_dir(instance_id) / "deployment_info.json"
    deployment_info: dict = {}
    if info_path.exists():
        deployment_info = json.loads(info_path.read_text())
    return evaluate_health(
        snapshot=snapshot,
        hub_domain=spec.hub_domain,
        lb_ip=deployment_info.get("lb_ip", ""),
        dns_pending=bool(deployment_info.get("dns_pending")),
        pipeline_state=status.state,
        probe_public=probe_public,
    )


__all__ = [
    "PipelineError",
    "mark_pipeline_failed",
    "validate_hetzner_token",
    "validate_spec",
    "run_pipeline",
    "harden_firewall",
    "destroy_cluster",
    "build_deployment_info",
    "get_ingress_load_balancer_info",
    "refresh_deployment_lb_ip",
    "build_secrets_zip",
    "build_debug_bundle",
    "get_health",
    "get_resources",
    "get_volumes_context",
    "sync_volume_inventory",
]
