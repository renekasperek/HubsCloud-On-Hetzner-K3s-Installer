from __future__ import annotations

import httpx

from services.providers.hetzner import api


class HetznerProvider:
    id = "hetzner"

    def validate_token(self, token: str) -> tuple[bool, str]:
        try:
            r = httpx.get(
                f"{api.HCLOUD_BASE}/datacenters",
                headers=api._headers(token),
                timeout=15.0,
            )
            if r.status_code == 200:
                return True, "Token valid"
            return False, f"Hetzner API returned {r.status_code}"
        except Exception as e:
            return False, str(e)

    def audit_cluster(self, token: str) -> dict:
        return api.audit_hetzner_cluster(token)

    def cluster_master_present(self, token: str) -> bool:
        return api.cluster_master_present(token)

    def pre_destroy_inventory(self, token: str) -> dict:
        cluster_ids = api.fetch_cluster_server_ids(token)
        load_balancers = api.find_cluster_load_balancers(token, cluster_ids)
        if not load_balancers:
            load_balancers = api.find_kubernetes_managed_load_balancers(token)
        persistent_volumes = api.find_persistent_data_volumes(token)
        return {
            "cluster_ids": cluster_ids,
            "load_balancers": load_balancers,
            "persistent_volumes": persistent_volumes,
        }

    def delete_post_terraform_extras(self, token: str, inventory: dict) -> dict:
        """Intentionally does not delete Kubernetes-managed LBs or CSI volumes.

        Those resources protect ingress routing and database data; operators remove
        them manually in Hetzner Console when they accept data loss.
        """
        return {
            "load_balancers_deleted": [],
            "volumes_deleted": [],
            "errors": [],
            "skipped": {
                "load_balancers": [
                    {"name": lb.get("name"), "id": lb.get("id")}
                    for lb in (inventory.get("load_balancers") or [])
                ],
                "volumes": [
                    {"name": v.get("name"), "id": v.get("id")}
                    for v in (inventory.get("persistent_volumes") or [])
                ],
            },
        }

    def force_delete_servers(self, token: str) -> list[str]:
        return api.force_delete_hcce_servers(token)
