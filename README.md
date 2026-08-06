# Hubs Installer

Self-contained Docker installer for Hubs Cloud Community Edition on Hetzner (k3s + external HAProxy + cert-manager + curated HCCE).

## Prerequisites

- Docker
- Hetzner Cloud API token
- Domain + DNS (configured after deploy)
- SMTP credentials

## Quick start

```bash
cd HubsCloud-On-Hetzner-K3s-Installer
docker compose up --build
```

Open **http://127.0.0.1:8080**

After `docker compose up --build`, the terminal may sit on **“Attaching to HCCE-on-Hetzner-installer”** with little or no output — that is normal. The container is running in the foreground; open the URL above in your browser. Press **Ctrl+C** in that terminal to stop it.

To run in the background instead:

```bash
docker compose up --build -d
docker compose logs -f   # follow logs
```

1. **Create new instance** — wizard collects credentials
2. **Create cluster** — provisions VMs, waits for k3s, automatically installs workloads
3. Live status — nodes, pods, certificates
4. **Download secrets ZIP** — passwords, kubeconfig, SSH keys, rendered manifests, and `README.txt` with the installer URL (store securely)

## Ports & volumes

- `127.0.0.1:8080` — UI + API (localhost only)
- `./data:/data` — instance state, secrets, kubeconfig, terraform state

## Security

- No authentication on localhost API (v1)
- Secrets never committed in `templates/`; runtime secrets only in `./data`
- Secrets ZIP contains **cleartext** passwords, kubeconfig, and **SSH private/public keys** under `ssh/` — treat as highly sensitive

### SSH keys in the secrets ZIP

The wizard **Generate key pair** step creates an Ed25519 key pair. The private key is used by the installer to fetch kubeconfig; both keys are included in the secrets ZIP at handoff:

```text
ssh/id_ed25519      — private key
ssh/id_ed25519.pub  — public key (on all nodes)
```

Direct node access (after provisioning):

```bash
chmod 600 ssh/id_ed25519
ssh -i ssh/id_ed25519 cluster@<node-public-ip>
```

See `README.txt` inside the ZIP for the master IP and installer progress URL. If you hardened the firewall **without** keeping port 22 open, direct SSH from the internet is blocked.

## Templates

Infrastructure and HCCE manifests ship in `installer/templates/` (baked into the image). See `templates/README.md` and `docs/BUILD.md`.

## Manage existing

Not implemented in v1 (stub only).

## Failure recovery

### Provisioning stuck on “Cluster ready”?

The installer creates **three Hetzner servers** (`hcce-master-db`, `hcce-web-worker`, `hcce-webrtc-worker`). All three must join the Kubernetes cluster before workloads install. This usually takes **10–15 minutes**; the WebRTC worker often finishes last.

If step 4 runs longer than that:

1. Open the **Cluster join progress** panel on the progress page — it shows which node is missing.
2. Click **Try automatic repair** (safe — does not delete servers). The installer fixes common issues (private network down, k3s not started) over SSH.
3. If still stuck, click **Stop waiting and mark as failed**, then **Retry provisioning**.
4. Download the **debug bundle** for support (logs + cluster join diagnostics, no passwords).
5. Last resort: delete `hcce-*` servers in [Hetzner Console](https://console.hetzner.cloud), then **Retry provisioning**.

Your Hetzner servers keep billing until you delete them in the Console. Half-built clusters are recoverable — you only save money after a Console delete.

**Stale servers:** Cloud-init only runs on first boot. If a previous run partially configured a VM (same IP, old disk state), retrying without recreating can leave workers stuck. The installer recreates worker VMs automatically when you **Retry provisioning** after a cluster-join failure. For a fully clean slate, delete all `hcce-*` resources in the Console first.

**SSH / host keys:** The installer ignores SSH host-key fingerprints (`StrictHostKeyChecking=no`). Connection failures are usually a **key mismatch** (regenerated installer key vs keys baked into an old VM) or the node still booting — not a fingerprint cache issue inside cloud-init (nodes do not SSH to each other).

### Firewall hardening failed?

If **Apply hardened firewall** fails, your cluster is still running. Click the button again, or leave the open provisioning firewall in place (less secure). Failures are logged on the progress page.

### Destroy cluster infrastructure

On the progress page, **Danger zone → Destroy cluster infrastructure** runs `terraform destroy` and removes:

- `hcce-*` servers, private network, firewall, SSH key resource, placement group (Terraform-managed)

**Not deleted on purpose** (created by Kubernetes, not Terraform):

- **Ingress load balancer(s)** — provisioned by the Hetzner CCM when HAProxy starts
- **CSI block volumes** — PostgreSQL, Reticulum, and backup data

Those resources **keep billing** after destroy. That is intentional: tearing down the cluster should not silently wipe your database. Delete load balancer(s) and block volume(s) manually in [Hetzner Console](https://console.hetzner.cloud) when you accept data loss and want billing to stop.

Wizard settings, secrets, SSH keys, and **`volumes-inventory.json`** under `./data` are **kept** so you can provision again immediately (optionally reattach CSI volumes in the wizard).

After destroy, the installer reports **success** when Terraform-managed resources are gone. The audit shows a **warning** (not a failure) if Kubernetes load balancer(s) and/or CSI volumes remain.

Before a **fresh** provision (no Terraform state on disk), provisioning is **blocked** only if `hcce-*` **servers** still exist without matching state.

If Terraform is still applying, wait for it to finish first. While stuck on cluster join (after Terraform), destroy is allowed — it stops provisioning and tears down infrastructure.

### Full teardown and retry (manual)

Your workflow for a clean restart: **delete all HCCE resources in the Hetzner Cloud Console**, then run the installer again. You do not need to run Terraform or SSH yourself.

1. In [Hetzner Console](https://console.hetzner.cloud): delete servers (`hcce-*`), load balancers, volumes, and the private network if you created one for this cluster.
2. In the installer: open your instance → **Retry provisioning** (or **Create cluster** on a new instance).
3. The installer detects that `hcce-master-db` is gone, **clears saved Terraform state** under `./data`, and runs a **fresh** `terraform apply`.

If you see **terraform output … not found** or **output not available**, that usually means Terraform never completed successfully while old state was still on disk. After a console delete, step 2 above fixes it — no manual `terraform apply`.

Other failures on the progress page:

- **Invalid server types** — open **Machines & SSH**, pick types from the live catalog, validate, then retry.
- **SSH / kubeconfig** — click **Generate key pair** in the wizard (step 3: Cluster).

**SSH / kubeconfig:** Click **Generate key pair**. The installer fetches kubeconfig over SSH, then hardens SSH on all nodes (disables root) from the pipeline.

**WebRTC (dialog/coturn):** The installer labels the master with `svccontroller.k3s.cattle.io/lbpool=master-only` before HAProxy is applied (same as `k3s-setup/configure-node-labels.sh`). Without this, k3s `svclb` binds ports 4443/5349 on the WebRTC node and dialog/coturn cannot start.

v1 re-runs the full pipeline on retry (does not resume mid-step).

## Cluster size presets

| Preset | Master | Web worker | WebRTC worker |
|--------|--------|------------|---------------|
| small | cx23 | cpx12 | cpx12 |
| medium | cpx13 | cx23 | cx23 |
| large | cpx32 | cx23 | cpx13 |

DNS handoff uses the **Hetzner Cloud load balancer public IP** from the Hetzner API (the Kubernetes service uses a private IP because `use-private-ip` is enabled on the LB service).

## License

This project is licensed under the [Mozilla Public License 2.0](./LICENSE).

Third-party tools and libraries used by the installer (Terraform, kubectl, Helm, Hetzner provider, Python/npm dependencies, and runtime cluster components) are listed in **[THIRD-PARTY-NOTICES.md](./THIRD-PARTY-NOTICES.md)** with their respective licenses.

## AI usage disclosure

This repository is **mostly AI-generated**. Templates started from manually edited Terraform (Hetzner tutorial lineage) and HCCE YAML (Hubs Foundation `hcce.yaml`), then were transcribed into Jinja2 by an agent. The UI, backend, docs, and this disclosure are agent output with human direction — not line-by-line human review.

See **[AI-DISCLOSURE.md](./AI-DISCLOSURE.md)** for the full, honest breakdown.
