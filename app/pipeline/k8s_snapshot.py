from __future__ import annotations

import json

from config import instance_dir
from pipeline.core import kube_env, run_cmd
from pipeline.deployment import resolve_ingress_lb, try_network_id
from services.storage import load_spec


def parse_nodes(data: dict) -> list:
    out = []
    for n in data.get("items", []):
        ready = "Unknown"
        for c in n.get("status", {}).get("conditions", []):
            if c.get("type") == "Ready":
                ready = c.get("status", "Unknown")
        out.append({"name": n["metadata"]["name"], "status": ready, "labels": n["metadata"].get("labels", {})})
    return out


def parse_pods(data: dict) -> list:
    out = []
    for i in data.get("items", []):
        reason = ""
        for cs in i.get("status", {}).get("containerStatuses") or []:
            waiting = cs.get("state", {}).get("waiting") or {}
            if waiting.get("reason"):
                reason = waiting["reason"]
                break
            terminated = cs.get("state", {}).get("terminated") or {}
            if terminated.get("reason") in ("Error", "CrashLoopBackOff"):
                reason = terminated["reason"]
                break
        out.append(
            {
                "namespace": i["metadata"]["namespace"],
                "name": i["metadata"]["name"],
                "status": i.get("status", {}).get("phase", "Unknown"),
                "node": i.get("spec", {}).get("nodeName", ""),
                "reason": reason,
            }
        )
    return out


def parse_deployments(data: dict) -> list:
    return [
        {
            "namespace": i["metadata"]["namespace"],
            "name": i["metadata"]["name"],
            "ready": f"{i.get('status', {}).get('readyReplicas', 0)}/{i.get('status', {}).get('replicas', 0)}",
        }
        for i in data.get("items", [])
    ]


def parse_ingresses(data: dict) -> list:
    return [
        {
            "namespace": i["metadata"]["namespace"],
            "name": i["metadata"]["name"],
            "hosts": [r.get("host") for r in i.get("spec", {}).get("rules", []) if r.get("host")],
        }
        for i in data.get("items", [])
    ]


def parse_certs(data: dict) -> list:
    out = []
    for i in data.get("items", []):
        ready = False
        for c in i.get("status", {}).get("conditions", []):
            if c.get("type") == "Ready" and c.get("status") == "True":
                ready = True
        out.append({"namespace": i["metadata"]["namespace"], "name": i["metadata"]["name"], "ready": ready})
    return out


def load_balancer_snapshot(instance_id: str) -> list[dict]:
    spec = load_spec(instance_id)
    if not spec.hetzner_api_token:
        return []
    network_id = try_network_id(instance_id)
    lb_ip, lb = resolve_ingress_lb(instance_id, spec, network_id)
    if lb_ip and lb:
        return [
            {
                "name": lb.get("name") or "haproxy-ingress-lb",
                "external_ip": lb_ip,
                "source": "hetzner_api",
                "id": lb.get("id"),
            }
        ]
    return [{"name": "haproxy-ingress-lb", "external_ip": "", "source": "hetzner_api", "note": "Public IP not resolved yet"}]


def get_resources(instance_id: str) -> dict:
    kc = instance_dir(instance_id) / "kubeconfig"
    if not kc.exists():
        return {"error": "kubeconfig not available", "nodes": [], "pods": [], "deployments": [], "ingresses": [], "certificates": [], "loadbalancers": []}
    env = kube_env(instance_id)
    snap = {"nodes": [], "pods": [], "deployments": [], "ingresses": [], "certificates": [], "loadbalancers": []}
    try:
        for kind, cmd, parser in [
            ("nodes", ["kubectl", "get", "nodes", "-o", "json"], parse_nodes),
            ("pods", ["kubectl", "get", "pods", "-A", "-o", "json"], parse_pods),
            ("deployments", ["kubectl", "get", "deployments", "-A", "-o", "json"], parse_deployments),
            ("ingresses", ["kubectl", "get", "ingress", "-A", "-o", "json"], parse_ingresses),
            ("certificates", ["kubectl", "get", "certificates", "-A", "-o", "json"], parse_certs),
        ]:
            result = run_cmd(cmd, env=env, timeout=60)
            if result.returncode == 0:
                snap[kind] = parser(json.loads(result.stdout))
        snap["loadbalancers"] = load_balancer_snapshot(instance_id)
    except Exception as e:
        snap["error"] = str(e)
    return snap
