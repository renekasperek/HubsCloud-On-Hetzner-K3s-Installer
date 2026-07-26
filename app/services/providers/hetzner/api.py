from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass

import httpx

from schemas.models import CLUSTER_SIZE_RECOMMENDATIONS
from services.providers.base import CLUSTER_SERVER_NAMES

HCLOUD_BASE = "https://api.hetzner.cloud/v1"
INGRESS_LB_LABELS = {"purpose": "ingress", "env": "prod"}
HCCE_NETWORK_NAMES = frozenset({"kubernetes-cluster"})
HCCE_FIREWALL_NAMES = frozenset({"open-firewall", "hcce-hardened-firewall"})
HCCE_PLACEMENT_GROUP_NAMES = frozenset({"kubernetes-group"})
HCCE_SSH_KEY_NAMES = frozenset({"h_cloud_key"})


def is_private_ip(ip: str) -> bool:
    if not ip:
        return True
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return True


def load_balancer_public_ipv4(lb: dict) -> str:
    pub = lb.get("public_net") or {}
    ipv4 = (pub.get("ipv4") or {}).get("ip") or ""
    return ipv4 if ipv4 and not is_private_ip(ipv4) else ""


def fetch_load_balancers(token: str) -> list[dict]:
    r = httpx.get(f"{HCLOUD_BASE}/load_balancers", headers=_headers(token), timeout=30.0)
    r.raise_for_status()
    return r.json().get("load_balancers", [])


def fetch_servers(token: str) -> list[dict]:
    r = httpx.get(f"{HCLOUD_BASE}/servers", headers=_headers(token), timeout=30.0)
    r.raise_for_status()
    return r.json().get("servers", [])


def fetch_cluster_server_ids(token: str) -> set[int]:
    names = set(CLUSTER_SERVER_NAMES)
    return {int(s["id"]) for s in fetch_servers(token) if s.get("name") in names}


def cluster_master_present(token: str) -> bool:
    """True if hcce-master-db still exists in Hetzner (cluster not console-wiped)."""
    return any(s.get("name") == "hcce-master-db" for s in fetch_servers(token))


def fetch_load_balancer(token: str, lb_id: int | str) -> dict:
    r = httpx.get(f"{HCLOUD_BASE}/load_balancers/{lb_id}", headers=_headers(token), timeout=20.0)
    r.raise_for_status()
    return r.json().get("load_balancer", {})


def _lb_target_server_ids(lb: dict) -> set[int]:
    ids: set[int] = set()
    for target in lb.get("targets") or []:
        if target.get("type") != "server":
            continue
        server_id = (target.get("server") or {}).get("id")
        if server_id is not None:
            ids.add(int(server_id))
    return ids


def _lb_listen_ports(lb: dict) -> set[int]:
    ports: set[int] = set()
    for service in lb.get("services") or []:
        listen_port = service.get("listen_port")
        if listen_port is not None:
            ports.add(int(listen_port))
    return ports


def _score_ingress_load_balancer(
    lb: dict,
    *,
    location: str = "",
    network_id: str | int | None = None,
    cluster_server_ids: set[int] | None = None,
    lb_name_hint: str | None = None,
) -> int:
    if not load_balancer_public_ipv4(lb):
        return -1

    score = 1
    lb_location = (lb.get("location") or {}).get("name", "")
    if location and lb_location == location:
        score += 20

    labels = lb.get("labels") or {}
    if labels.get("purpose") == "ingress":
        score += 15
    if labels.get("env") == "prod":
        score += 5

    if network_id and str(network_id) not in ("", "0"):
        net_id = int(network_id)
        private_nets = lb.get("private_net") or []
        if any(int(p.get("network", 0)) == net_id for p in private_nets):
            score += 25

    name = (lb.get("name") or "").lower()
    if lb_name_hint and lb_name_hint.lower() == name:
        score += 50
    elif lb_name_hint and lb_name_hint.lower() in name:
        score += 30
    if any(token in name for token in ("haproxy", "ingress")):
        score += 10

    ports = _lb_listen_ports(lb)
    if 80 in ports or 443 in ports:
        score += 10

    if cluster_server_ids:
        overlap = _lb_target_server_ids(lb) & cluster_server_ids
        if overlap:
            score += 25 + len(overlap) * 5

    return score


def find_ingress_load_balancer(
    token: str,
    location: str = "",
    network_id: str | int | None = None,
    *,
    lb_name: str | None = None,
    cluster_server_ids: set[int] | None = None,
) -> dict | None:
    """Find the HAProxy ingress load balancer via Hetzner API (not kubectl svc status)."""
    load_balancers = fetch_load_balancers(token)

    if lb_name:
        for lb in load_balancers:
            if lb.get("name") == lb_name and load_balancer_public_ipv4(lb):
                return lb

    if cluster_server_ids is None:
        try:
            cluster_server_ids = fetch_cluster_server_ids(token)
        except httpx.HTTPError:
            cluster_server_ids = set()

    best: dict | None = None
    best_score = -1
    for lb in load_balancers:
        score = _score_ingress_load_balancer(
            lb,
            location=location,
            network_id=network_id,
            cluster_server_ids=cluster_server_ids,
            lb_name_hint=lb_name,
        )
        if score > best_score:
            best_score = score
            best = lb

    if best is not None and best_score >= 11:
        return best

    # Fallback: exactly one public LB in the requested location.
    location_matches = [
        lb
        for lb in load_balancers
        if load_balancer_public_ipv4(lb) and (not location or (lb.get("location") or {}).get("name") == location)
    ]
    if len(location_matches) == 1:
        return location_matches[0]

    return None


def resolve_ingress_load_balancer_ip(
    token: str,
    location: str = "",
    network_id: str | int | None = None,
    *,
    lb_id: str | int | None = None,
    lb_name: str | None = None,
) -> str:
    """Return the public IPv4 of the ingress load balancer, if available."""
    if lb_id:
        try:
            lb = fetch_load_balancer(token, lb_id)
            ip = load_balancer_public_ipv4(lb)
            if ip:
                return ip
        except httpx.HTTPError:
            pass
    lb = find_ingress_load_balancer(token, location, network_id, lb_name=lb_name)
    return load_balancer_public_ipv4(lb) if lb else ""


def wait_for_ingress_load_balancer_ip(
    token: str,
    location: str = "",
    network_id: str | int | None = None,
    *,
    lb_id: str | int | None = None,
    lb_name: str | None = None,
    timeout: int = 600,
    poll_interval: int = 10,
) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        ip = resolve_ingress_load_balancer_ip(
            token,
            location,
            network_id,
            lb_id=lb_id,
            lb_name=lb_name,
        )
        if ip:
            return ip
        time.sleep(poll_interval)
    return ""


@dataclass
class ServerTypeOption:
    name: str
    description: str
    cores: int
    memory: float
    disk: int
    category: str
    available: bool
    recommended: bool
    price_monthly_gross: str | None
    deprecated: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "cores": self.cores,
            "memory": self.memory,
            "disk": self.disk,
            "category": self.category,
            "available": self.available,
            "recommended": self.recommended,
            "price_monthly_gross": self.price_monthly_gross,
            "deprecated": self.deprecated,
        }


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def fetch_locations(token: str) -> list[dict]:
    r = httpx.get(f"{HCLOUD_BASE}/locations", headers=_headers(token), timeout=20.0)
    r.raise_for_status()
    return [
        {
            "name": loc["name"],
            "description": loc.get("description", ""),
            "city": loc.get("city", ""),
            "country": loc.get("country", ""),
        }
        for loc in r.json().get("locations", [])
    ]


def fetch_server_types_for_location(token: str, location: str) -> list[ServerTypeOption]:
    r = httpx.get(f"{HCLOUD_BASE}/server_types", headers=_headers(token), timeout=30.0)
    r.raise_for_status()
    options: list[ServerTypeOption] = []
    for st in r.json().get("server_types", []):
        loc_entry = next((l for l in st.get("locations", []) if l.get("name") == location), None)
        if loc_entry is None:
            continue
        price = next((p for p in st.get("prices", []) if p.get("location") == location), None)
        monthly = None
        if price and price.get("price_monthly"):
            monthly = price["price_monthly"].get("gross")
        deprecated = loc_entry.get("deprecation") is not None
        options.append(
            ServerTypeOption(
                name=st["name"],
                description=st.get("description", st["name"]),
                cores=int(st.get("cores", 0)),
                memory=float(st.get("memory", 0)),
                disk=int(st.get("disk", 0)),
                category=st.get("category", ""),
                available=bool(loc_entry.get("available", False)),
                recommended=bool(loc_entry.get("recommended", False)),
                price_monthly_gross=monthly,
                deprecated=deprecated,
            )
        )
    # Prefer available, non-deprecated, x86 shared-ish; sort by cores then memory
    options.sort(key=lambda o: (not o.available, o.deprecated, o.cores, o.memory, o.name))
    return options


def cluster_size_recommendations() -> dict[str, dict[str, dict[str, int]]]:
    """Static vCPU/RAM guidance per cluster size — not tied to Hetzner type names."""
    return {size: dict(roles) for size, roles in CLUSTER_SIZE_RECOMMENDATIONS.items()}


def estimate_cluster_monthly_cost(
    token: str,
    location: str,
    master: str,
    web: str,
    webrtc: str,
) -> str:
    """Sum gross monthly server prices for the three node types at a location."""
    try:
        options = {o.name: o for o in fetch_server_types_for_location(token, location)}
    except httpx.HTTPError:
        return ""
    total = 0.0
    for name in (master, webrtc, web):
        opt = options.get(name)
        if not opt or not opt.price_monthly_gross:
            return ""
        total += float(opt.price_monthly_gross)
    return f"{total:.2f}"


def validate_server_types(
    token: str,
    location: str,
    master: str,
    web: str,
    webrtc: str,
) -> tuple[bool, str, list[str]]:
    """Return ok, message, list of invalid type names."""
    if not (location or "").strip():
        return False, "Choose a Hetzner location first", []

    messages: list[str] = []
    invalid: list[str] = []
    for role, name in [("master", master), ("web", web), ("webrtc", webrtc)]:
        if not (name or "").strip():
            invalid.append(name or role)
            messages.append(f"{role}: choose a server type for this location")

    if messages:
        return False, "; ".join(messages), invalid

    try:
        options = {o.name: o for o in fetch_server_types_for_location(token, location)}
    except httpx.HTTPError as e:
        return False, f"Could not fetch server types: {e}", []

    for role, name in [("master", master), ("web", web), ("webrtc", webrtc)]:
        opt = options.get(name)
        if opt is None:
            invalid.append(name)
            messages.append(f"{role}: '{name}' is not offered in {location}")
        elif opt.deprecated:
            invalid.append(name)
            messages.append(f"{role}: '{name}' is deprecated in {location}")
        elif not opt.available:
            invalid.append(name)
            messages.append(f"{role}: '{name}' is currently unavailable in {location}")

    if invalid:
        return False, "; ".join(messages), invalid
    return True, "All server types valid for this location", []


def server_public_ip(server: dict) -> str:
    pub = server.get("public_net") or {}
    return (pub.get("ipv4") or {}).get("ip") or ""


def server_private_ip(server: dict) -> str:
    for net in server.get("private_net") or []:
        ip = net.get("ip") or ""
        if ip:
            return ip
    return ""


def fetch_cluster_servers(token: str) -> dict[str, dict]:
    """Return hcce-* servers keyed by name."""
    names = set(CLUSTER_SERVER_NAMES)
    return {s["name"]: s for s in fetch_servers(token) if s.get("name") in names}


def fetch_server(token: str, server_id: int | str) -> dict:
    r = httpx.get(f"{HCLOUD_BASE}/servers/{server_id}", headers=_headers(token), timeout=20.0)
    r.raise_for_status()
    return r.json().get("server", {})


def collect_cluster_volume_ids(token: str) -> list[int]:
    """Volume IDs attached to hcce-* servers (CSI / HCCE block volumes)."""
    volume_ids: list[int] = []
    for summary in fetch_servers(token):
        if summary.get("name") not in CLUSTER_SERVER_NAMES:
            continue
        detail = fetch_server(token, summary["id"])
        for vol in detail.get("volumes") or []:
            vid = int(vol) if isinstance(vol, int) else int((vol or {}).get("id", 0))
            if vid and vid not in volume_ids:
                volume_ids.append(vid)
    return volume_ids


def find_cluster_load_balancers(token: str, cluster_server_ids: set[int]) -> list[dict]:
    """Load balancers targeting cluster nodes or tagged as ingress."""
    matched: list[dict] = []
    seen: set[int] = set()
    for lb in fetch_load_balancers(token):
        lb_id = int(lb.get("id") or 0)
        if not lb_id or lb_id in seen:
            continue
        labels = lb.get("labels") or {}
        targets = _lb_target_server_ids(lb)
        if (cluster_server_ids and targets & cluster_server_ids) or labels.get("purpose") == "ingress":
            matched.append(lb)
            seen.add(lb_id)
    return matched


def delete_load_balancer(token: str, lb_id: int | str) -> None:
    r = httpx.delete(f"{HCLOUD_BASE}/load_balancers/{lb_id}", headers=_headers(token), timeout=120.0)
    r.raise_for_status()


def delete_volume(token: str, volume_id: int | str) -> None:
    r = httpx.delete(f"{HCLOUD_BASE}/volumes/{volume_id}", headers=_headers(token), timeout=120.0)
    r.raise_for_status()


def fetch_networks(token: str) -> list[dict]:
    r = httpx.get(f"{HCLOUD_BASE}/networks", headers=_headers(token), timeout=30.0)
    r.raise_for_status()
    return r.json().get("networks", [])


def fetch_firewalls(token: str) -> list[dict]:
    r = httpx.get(f"{HCLOUD_BASE}/firewalls", headers=_headers(token), timeout=30.0)
    r.raise_for_status()
    return r.json().get("firewalls", [])


def fetch_volumes(token: str) -> list[dict]:
    r = httpx.get(f"{HCLOUD_BASE}/volumes", headers=_headers(token), timeout=30.0)
    r.raise_for_status()
    return r.json().get("volumes", [])


def fetch_placement_groups(token: str) -> list[dict]:
    r = httpx.get(f"{HCLOUD_BASE}/placement_groups", headers=_headers(token), timeout=30.0)
    r.raise_for_status()
    return r.json().get("placement_groups", [])


def fetch_ssh_keys(token: str) -> list[dict]:
    r = httpx.get(f"{HCLOUD_BASE}/ssh_keys", headers=_headers(token), timeout=30.0)
    r.raise_for_status()
    return r.json().get("ssh_keys", [])


def delete_server(token: str, server_id: int | str) -> None:
    r = httpx.delete(f"{HCLOUD_BASE}/servers/{server_id}", headers=_headers(token), timeout=120.0)
    r.raise_for_status()


def delete_network(token: str, network_id: int | str) -> None:
    r = httpx.delete(f"{HCLOUD_BASE}/networks/{network_id}", headers=_headers(token), timeout=120.0)
    r.raise_for_status()


def delete_firewall(token: str, firewall_id: int | str) -> None:
    r = httpx.delete(f"{HCLOUD_BASE}/firewalls/{firewall_id}", headers=_headers(token), timeout=120.0)
    r.raise_for_status()


def find_kubernetes_managed_load_balancers(token: str) -> list[dict]:
    """Ingress load balancers created by Kubernetes CCM (not Terraform)."""
    matched: list[dict] = []
    seen: set[int] = set()
    for lb in fetch_load_balancers(token):
        lb_id = int(lb.get("id") or 0)
        if not lb_id or lb_id in seen:
            continue
        labels = lb.get("labels") or {}
        name = (lb.get("name") or "").lower()
        ports = _lb_listen_ports(lb)
        if (
            labels.get("purpose") == "ingress"
            or "haproxy" in name
            or "ingress" in name
            or (ports & {80, 443} and not _lb_target_server_ids(lb))
        ):
            matched.append(lb)
            seen.add(lb_id)
    return matched


def find_persistent_data_volumes(token: str) -> list[dict]:
    """Block volumes provisioned by Kubernetes CSI (PostgreSQL / Reticulum data)."""
    out: list[dict] = []
    for vol in fetch_volumes(token):
        labels = vol.get("labels") or {}
        name = (vol.get("name") or "").lower()
        label_keys = " ".join(labels.keys()).lower()
        is_k8s = name.startswith("pvc-") or "kubernetes" in label_keys or "csi" in label_keys
        if not is_k8s:
            continue
        out.append(vol)
    return out


def audit_hetzner_cluster(token: str) -> dict:
    """Scan Hetzner for HCCE installer resources.

    ``clean`` means Terraform-managed resources are gone (safe to reprovision).
    Load balancers and CSI volumes may remain after destroy — reported as billable leftovers.
    """
    blocking: list[str] = []
    warnings: list[str] = []

    servers = [s for s in fetch_servers(token) if s.get("name") in CLUSTER_SERVER_NAMES]
    for s in servers:
        blocking.append(f"Server still exists: {s.get('name')} ({s.get('id')})")

    networks = [n for n in fetch_networks(token) if n.get("name") in HCCE_NETWORK_NAMES]
    for n in networks:
        blocking.append(f"Private network still exists: {n.get('name')} ({n.get('id')})")

    firewalls = [f for f in fetch_firewalls(token) if f.get("name") in HCCE_FIREWALL_NAMES]
    for f in firewalls:
        blocking.append(f"Firewall still exists: {f.get('name')} ({f.get('id')})")

    placement_groups = [g for g in fetch_placement_groups(token) if g.get("name") in HCCE_PLACEMENT_GROUP_NAMES]
    for g in placement_groups:
        blocking.append(f"Placement group still exists: {g.get('name')} ({g.get('id')})")

    ssh_keys = [k for k in fetch_ssh_keys(token) if k.get("name") in HCCE_SSH_KEY_NAMES]
    for k in ssh_keys:
        blocking.append(f"SSH key still exists: {k.get('name')} ({k.get('id')})")

    cluster_ids = {int(s["id"]) for s in servers}
    if cluster_ids:
        load_balancers = find_cluster_load_balancers(token, cluster_ids)
    else:
        load_balancers = find_kubernetes_managed_load_balancers(token)

    volumes_attached = collect_cluster_volume_ids(token) if servers else []
    persistent_volumes = find_persistent_data_volumes(token) if not servers else []
    volume_ids = volumes_attached if servers else [int(v["id"]) for v in persistent_volumes]

    if not servers:
        for lb in load_balancers:
            warnings.append(
                f"Load balancer still billing: {lb.get('name')} ({lb.get('id')}) — created by Kubernetes, not deleted on destroy"
            )
        for vid in volume_ids:
            warnings.append(
                f"Block volume still billing: {vid} — database / persistent data kept on purpose; delete in Hetzner Console if no longer needed"
            )

    has_billable_leftovers = bool(warnings) and not servers

    return {
        "clean": len(blocking) == 0,
        "issues": blocking,
        "warnings": warnings,
        "has_billable_leftovers": has_billable_leftovers,
        "servers": [{"name": s.get("name"), "id": s.get("id")} for s in servers],
        "networks": [{"name": n.get("name"), "id": n.get("id")} for n in networks],
        "firewalls": [{"name": f.get("name"), "id": f.get("id")} for f in firewalls],
        "load_balancers": [{"name": lb.get("name"), "id": lb.get("id")} for lb in load_balancers],
        "volumes": volume_ids,
        "placement_groups": [{"name": g.get("name"), "id": g.get("id")} for g in placement_groups],
        "ssh_keys": [{"name": k.get("name"), "id": k.get("id")} for k in ssh_keys],
    }


def force_delete_hcce_servers(token: str) -> list[str]:
    """Delete hcce-* servers by name when Terraform state is missing."""
    deleted: list[str] = []
    for s in fetch_servers(token):
        if s.get("name") not in CLUSTER_SERVER_NAMES:
            continue
        delete_server(token, s["id"])
        deleted.append(s["name"])
    return deleted
