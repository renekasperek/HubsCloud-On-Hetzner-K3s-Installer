# Architecture (v1)

## Components

| Layer | Role |
|-------|------|
| React SPA | Harbor Desk wizard, progress, live snapshot |
| FastAPI | REST API, background pipeline, static file serve |
| Jinja2 renderers | `templates/` → `/data/instances/<id>/` |
| Pipeline | terraform, kubectl, helm subprocesses |
| `/data` volume | spec, secrets, kubeconfig, tfstate, logs |

## Flow

1. User completes wizard → `spec.json`
2. **Create cluster** → async pipeline job
3. Phase A: validate → render → terraform → wait nodes → kubeconfig
4. Phase B: labels → CCM/CSI → HAProxy → cert-manager → HCCE (automatic)
5. UI polls status (2s), resources + health (4s)
6. Handoff: DNS checklist + health summary + secrets ZIP

## Templates

Shipped in `installer/templates/`, copied to `/opt/templates` at image build. Curated HCCE from this cluster’s stack (HAProxy, cert-manager, pgsql-backup). No `hubs-cloud` / `gen-hcce`.

## Cloud providers

Terraform templates live under `installer/templates/terraform/` (Hetzner `hcloud_*` resources today). A **provider layer** in `app/services/providers/` isolates cloud API calls from pipeline orchestration so a second provider (e.g. Hostinger) can be added later without rewriting the wizard or progress UI.

| Piece | Role |
|-------|------|
| `providers/base.py` | `CloudProvider` protocol, shared cluster server names |
| `providers/registry.py` | `get_cloud_provider(spec)` — Hetzner only for now |
| `providers/hetzner/` | Hetzner Cloud API client + `HetznerProvider` |
| `services/hetzner.py` | Backward-compatible re-exports |

Pipeline modules under `app/pipeline/` call `get_cloud_provider()` for audit, destroy, and pre-provision checks. Catalog endpoints (locations, server types) still import Hetzner helpers directly until a second provider exists.

## Pipeline modules

| Module | Role |
|--------|------|
| `runner.py` | Thin re-exports for API routes |
| `provision.py` | Main provisioning flow |
| `destroy.py` | Terraform destroy + cloud cleanup |
| `firewall.py` | Post-provision firewall hardening |
| `cluster_ops.py` | Kubeconfig fetch, node wait, SSH hardening |
| `workloads.py` | CCM/CSI, cert-manager, kubectl apply |
| `deployment.py` | LB resolution, deployment info |
| `k8s_snapshot.py` | Health/resources snapshot |
| `bundles.py` | Secrets ZIP, debug bundle |
| `cluster_repair.py` | One-click cluster join repair |

Shared SSH helpers live in `services/ssh.py`.

## Security model

Localhost-trusted, no API auth. Secrets only on `./data` volume.
