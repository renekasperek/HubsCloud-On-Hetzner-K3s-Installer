from __future__ import annotations

from schemas.models import InstanceSpec
from services.providers.base import CloudProvider
from services.providers.hetzner.provider import HetznerProvider

_PROVIDERS: dict[str, CloudProvider] = {
    "hetzner": HetznerProvider(),
}


def get_cloud_provider(spec: InstanceSpec) -> CloudProvider:
    """Return the cloud provider for this instance (Hetzner today; Hostinger later)."""
    provider_id = getattr(spec, "cloud_provider", None) or "hetzner"
    if provider_id in _PROVIDERS:
        return _PROVIDERS[provider_id]
    if spec.hetzner_api_token:
        return _PROVIDERS["hetzner"]
    raise ValueError(f"Unknown or unconfigured cloud provider: {provider_id}")
