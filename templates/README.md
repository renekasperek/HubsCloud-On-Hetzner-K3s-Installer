# Template placeholder contract

Jinja2 templates under this directory are rendered by the installer API into `/data/instances/<id>/`.

## Terraform (`terraform/`)

| Placeholder | Source |
|-------------|--------|
| `hetzner_api_token` | spec |
| `k3s_token` | secrets |
| `ssh_public_key_path` | instance `/data/.../ssh/id_ed25519.pub` |
| `ssh_private_key_path` | instance `/data/.../ssh/id_ed25519` |
| `firewall_hardened`, `firewall_allow_ssh` | spec (open firewall during provisioning; hardened via progress UI) |
| `location` | spec |
| `master_server_type` | spec preset or override |
| `webrtc_server_type` | spec preset or override |
| `web_server_type` | spec preset or override |

## Platform K8s (`k8s/`)

| Placeholder | Source |
|-------------|--------|
| `admin_email` | spec |
| `hetzner_api_token` | spec |
| `private_network_id` | terraform output after apply |
| `location` | spec |

## HCCE (`hcce/hcce.yaml.j2`)

| Placeholder | Source |
|-------------|--------|
| `hub_domain` | spec |
| `admin_email` | spec |
| `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_from` | spec |
| `db_password`, `node_cookie`, `guardian_key`, `phx_key` | secrets |
| `reticulum_image`, `hubs_image`, `spoke_image` | resolved from `core_app_images` in spec |
| `sketchfab_api_key`, `tenor_api_key` | spec |
| `pgsql_volume_size`, `reticulum_volume_size`, `pgsql_backup_volume_size` | spec |
| `perms_key`, `pgrst_jwt_secret` | generated once in `secrets.json`; PEM stored as one line with `\\n` (matches `k3s-setup/hcce/hcce.yaml`) |

## Pipeline apply order

1. `k8s/ccm/secret.yaml` + CCM manifest (URL)
2. `k8s/csi/secret.yaml` + Helm `hcloud-csi` + `k8s/csi/storageclass.yaml`
3. `k8s/metrics-server/*.yaml`
4. `k8s/haproxy/*.yaml` (rendered LB service)
5. Helm cert-manager + `k8s/cert-manager/cluster-issuer.yaml`
6. `rendered/hcce.yaml`

All values must be placeholders in committed templates — no live credentials.
