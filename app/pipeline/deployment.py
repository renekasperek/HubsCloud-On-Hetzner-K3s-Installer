from __future__ import annotations

import json
import time

from config import instance_dir
from pipeline.core import PipelineError, kube_env, run_cmd
from pipeline.terraform_ops import terraform_output
from schemas.models import InstanceSpec
from services.providers.hetzner.api import (
    fetch_load_balancer,
    find_ingress_load_balancer,
    is_private_ip,
    load_balancer_public_ipv4,
)
from services.storage import append_log, load_spec, save_deployment_info


def build_deployment_info(
    spec: InstanceSpec,
    *,
    lb_ip: str,
    master_ip: str,
    network_id: str,
) -> dict:
    dns_target = lb_ip if lb_ip and not is_private_ip(lb_ip) else ""
    dns_records = []
    if dns_target:
        for host in (
            spec.hub_domain,
            f"assets.{spec.hub_domain}",
            f"stream.{spec.hub_domain}",
            f"cors.{spec.hub_domain}",
        ):
            dns_records.append({"host": host, "type": "A", "target": dns_target})
    return {
        "hub_domain": spec.hub_domain,
        "admin_url": f"https://{spec.hub_domain}",
        "lb_ip": dns_target,
        "master_ip": master_ip,
        "network_id": network_id,
        "location": spec.location,
        "dns_records": dns_records,
        "dns_pending": not bool(dns_target),
    }


def k8s_haproxy_lb_hints(instance_id: str) -> dict[str, str]:
    result = run_cmd(
        ["kubectl", "get", "svc", "-n", "haproxy", "haproxy-ingress-lb", "-o", "json"],
        env=kube_env(instance_id),
        timeout=30,
    )
    if result.returncode != 0:
        return {}
    data = json.loads(result.stdout)
    annotations = data.get("metadata", {}).get("annotations", {})
    return {
        "name": annotations.get("load-balancer.hetzner.cloud/name", ""),
        "network": annotations.get("load-balancer.hetzner.cloud/network", ""),
        "location": annotations.get("load-balancer.hetzner.cloud/location", ""),
        "id": annotations.get("load-balancer.hetzner.cloud/id", ""),
    }


def try_network_id(instance_id: str) -> str:
    hints = k8s_haproxy_lb_hints(instance_id)
    network_id = hints.get("network") or ""
    if network_id and str(network_id) not in ("0", ""):
        return str(network_id)
    info_path = instance_dir(instance_id) / "deployment_info.json"
    if info_path.exists():
        info = json.loads(info_path.read_text())
        network_id = info.get("network_id")
        if network_id and str(network_id) not in ("0", ""):
            return str(network_id)
    try:
        network_id = terraform_output(instance_id, "private_network_id")
        if network_id and str(network_id) not in ("0", ""):
            return str(network_id)
    except PipelineError:
        pass
    return ""


def resolve_ingress_lb(instance_id: str, spec: InstanceSpec, network_id: str = "") -> tuple[str, dict | None]:
    hints = k8s_haproxy_lb_hints(instance_id)
    location = hints.get("location") or spec.location
    lb_name = hints.get("name") or None
    lb_id = hints.get("id") or None

    lb = None
    if lb_id:
        try:
            lb = fetch_load_balancer(spec.hetzner_api_token, lb_id)
        except Exception:
            lb = None
    if lb is None:
        lb = find_ingress_load_balancer(
            spec.hetzner_api_token,
            location,
            network_id or None,
            lb_name=lb_name,
        )
    if not lb:
        return "", None
    return load_balancer_public_ipv4(lb), lb


def get_ingress_load_balancer_info(instance_id: str) -> dict:
    spec = load_spec(instance_id)
    if not spec.hetzner_api_token:
        return {"found": False, "public_ip": "", "load_balancer": None, "error": "missing token"}
    network_id = try_network_id(instance_id)
    ip, lb = resolve_ingress_lb(instance_id, spec, network_id)
    if not lb:
        return {"found": False, "public_ip": "", "load_balancer": None}
    return {
        "found": True,
        "public_ip": ip,
        "load_balancer": {
            "id": lb.get("id"),
            "name": lb.get("name"),
            "location": (lb.get("location") or {}).get("name"),
            "labels": lb.get("labels", {}),
            "targets": len(lb.get("targets") or []),
        },
    }


def refresh_deployment_lb_ip(instance_id: str) -> dict | None:
    info_path = instance_dir(instance_id) / "deployment_info.json"
    if not info_path.exists():
        return None
    info = json.loads(info_path.read_text())
    spec = load_spec(instance_id)
    if not spec.hetzner_api_token:
        return info
    network_id = try_network_id(instance_id)
    lb_ip, _lb = resolve_ingress_lb(instance_id, spec, network_id)
    if not lb_ip:
        return info
    current = info.get("lb_ip") or ""
    current_target = (info.get("dns_records") or [{}])[0].get("target", "") if info.get("dns_records") else ""
    if lb_ip == current and lb_ip == current_target and not info.get("dns_pending"):
        return info
    updated = build_deployment_info(
        spec,
        lb_ip=lb_ip,
        master_ip=info.get("master_ip", ""),
        network_id=network_id,
    )
    save_deployment_info(instance_id, updated)
    return updated


def wait_lb_public_ip(instance_id: str, spec: InstanceSpec, network_id: str, timeout: int = 600) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        lb_ip, lb = resolve_ingress_lb(instance_id, spec, network_id)
        if lb_ip:
            lb_name = (lb or {}).get("name", "unknown")
            append_log(instance_id, f"Hetzner load balancer {lb_name} public IP: {lb_ip}")
            return lb_ip
        time.sleep(10)
    append_log(instance_id, "Timed out waiting for Hetzner load balancer public IP")
    return ""
