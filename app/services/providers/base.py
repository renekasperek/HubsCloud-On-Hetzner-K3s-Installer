from __future__ import annotations

from typing import Protocol, runtime_checkable

# Terraform server resource names (shared by cluster join diagnostics and cloud API scans).
CLUSTER_SERVER_NAMES = frozenset(
    {
        "hcce-master-db",
        "hcce-webrtc-worker",
        "hcce-web-worker",
    }
)


@runtime_checkable
class CloudProvider(Protocol):
    """Cloud API surface used by the provisioning pipeline (Terraform remains provider-specific templates)."""

    id: str

    def validate_token(self, token: str) -> tuple[bool, str]: ...

    def audit_cluster(self, token: str) -> dict: ...

    def cluster_master_present(self, token: str) -> bool: ...

    def pre_destroy_inventory(self, token: str) -> dict: ...

    def delete_post_terraform_extras(self, token: str, inventory: dict) -> dict: ...

    def force_delete_servers(self, token: str) -> list[str]: ...
