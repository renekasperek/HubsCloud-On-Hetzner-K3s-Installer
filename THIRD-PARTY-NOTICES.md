# Third-Party Notices

This file lists software and materials **used by** the Hubs Cloud on Hetzner K3s Installer. It is for attribution and license awareness only — **not legal advice**.

**This repository’s own source** (Python backend, React UI source, Jinja2/Terraform templates, and documentation authored for this project) is licensed under the [Mozilla Public License 2.0](./LICENSE), unless a file states otherwise.

Using or redistributing third-party components is subject to **their** licenses, independent of MPL 2.0 on our source.

---

## 1. Binaries bundled in the Docker image

The `Dockerfile` downloads and installs these CLI tools into the runtime image. They are **not** MPL-licensed.

| Component | Version (pinned in Dockerfile) | License | Project |
|-----------|-------------------------------|---------|---------|
| **Terraform** | 1.9.8 | [BUSL-1.1](https://www.hashicorp.com/en/license) (Business Source License) | [HashiCorp Terraform](https://www.terraform.io/) |
| **kubectl** | Latest stable at build time | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | [Kubernetes](https://kubernetes.io/) |
| **Helm** | 3.x (install script) | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | [Helm](https://helm.sh/) |

Base image: `python:3.12-slim-bookworm` (Debian-based; see [Docker Official Images](https://hub.docker.com/_/python) and Debian license terms for the OS layer).

UI build stage: `node:22-bookworm` (see [Node.js license](https://github.com/nodejs/node/blob/main/LICENSE)).

---

## 2. Python dependencies (runtime)

Installed from `app/requirements.txt` into the Docker image. Transitive dependencies also apply; run `pip licenses` in a built image for a full SBOM if needed.

| Package | Declared version | Typical license | Project |
|---------|------------------|-----------------|---------|
| fastapi | 0.115.6 | MIT | https://github.com/tiangolo/fastapi |
| uvicorn | 0.34.0 | BSD-3-Clause | https://github.com/encode/uvicorn |
| pydantic | 2.10.4 | MIT | https://github.com/pydantic/pydantic |
| pydantic-settings | 2.7.0 | MIT | https://github.com/pydantic/pydantic-settings |
| jinja2 | 3.1.5 | BSD-3-Clause | https://github.com/pallets/jinja |
| httpx | 0.28.1 | BSD-3-Clause | https://github.com/encode/httpx |
| cryptography | 44.0.0 | Apache-2.0 / BSD-3-Clause | https://github.com/pyca/cryptography |
| python-multipart | 0.0.20 | Apache-2.0 | https://github.com/Kludex/python-multipart |
| PyYAML | 6.0.2 | MIT | https://github.com/yaml/pyyaml |

---

## 3. Frontend build dependencies

The UI is built with Vite and bundled into static assets in the image. Source is not shipped at runtime; minified JS/CSS is served from `app/ui/dist/`.

Direct dependencies from `app/ui/package.json`:

| Package | Typical license | Project |
|---------|-----------------|---------|
| react, react-dom | MIT | https://github.com/facebook/react |
| react-router-dom | MIT | https://github.com/remix-run/react-router |
| marked | MIT | https://github.com/markedjs/marked |
| @fontsource/inter | OFL-1.1 (font) | https://fontsource.org/fonts/inter |
| @fontsource/jetbrains-mono | OFL-1.1 (font) | https://fontsource.org/fonts/jetbrains-mono |

Build tooling (devDependencies: vite, typescript, @vitejs/plugin-react) is used only at image build time.

---

## 4. Terraform provider (downloaded at provision time)

When the installer runs `terraform init` per instance, it downloads:

| Component | Pinned version | License | Project |
|-----------|----------------|---------|---------|
| **hetznercloud/hcloud** provider | 1.67.0 (`templates/terraform/main.tf`) | [MPL-2.0](https://github.com/hetznercloud/terraform-provider-hcloud/blob/main/LICENSE) | https://github.com/hetznercloud/terraform-provider-hcloud |

The provider binary is cached under each instance’s Terraform working directory (`/data/instances/<id>/terraform/.terraform/`), not committed to this repository.

---

## 5. Components installed during cluster provisioning

These are fetched or applied **at runtime** when a user provisions a cluster. They are not source files in this repo.

| Component | How installed | License (upstream) | Source |
|-----------|---------------|-------------------|--------|
| **k3s** | cloud-init on Hetzner VMs | Apache-2.0 | https://github.com/k3s-io/k3s |
| **hcloud Cloud Controller Manager** | `kubectl apply` of release manifest v1.23.0 | See upstream repo | https://github.com/hetznercloud/hcloud-cloud-controller-manager |
| **hcloud CSI driver** | Helm chart `hcloud/hcloud-csi` from `charts.hetzner.cloud` | See upstream repo | https://github.com/hetznercloud/csi-driver |
| **cert-manager** | Helm chart `jetstack/cert-manager` | Apache-2.0 | https://github.com/cert-manager/cert-manager |
| **metrics-server** | kubectl apply from `templates/k8s/metrics-server/` | Apache-2.0 (upstream Kubernetes SIGs manifest lineage) | https://github.com/kubernetes-sigs/metrics-server |
| **HAProxy Ingress Controller** | kubectl apply from `templates/k8s/haproxy/` | See upstream (HAProxy Technologies Kubernetes ingress) | https://github.com/haproxytech/kubernetes-ingress |

Exact chart and image versions are resolved by Helm/registry at install time unless pinned in templates.

---

## 6. Hetzner Cloud API and services

| Component | Use in installer | Terms |
|-----------|------------------|-------|
| **Hetzner Cloud REST API** | Python client in `app/services/providers/hetzner/api.py` (via `httpx`) | [Hetzner legal / Cloud terms](https://www.hetzner.com/legal) |
| **Hetzner Cloud infrastructure** | VMs, networks, firewalls, load balancers, volumes created by Terraform | Billed to the user’s Hetzner account; governed by Hetzner terms |

The installer does **not** bundle the `hcloud` CLI. Interaction with Hetzner is via the API and Terraform provider.

---

## 7. Upstream template and manifest lineage

Files under `templates/` adapt material from third-party sources. Our committed templates are MPL-2.0 **as part of this project**, but provenance matters:

| Source | Used for | Upstream license |
|--------|----------|------------------|
| **Hubs Foundation HCCE `hcce.yaml`** | Base for `templates/hcce/hcce.yaml.j2` | MPL-2.0 (Hubs Foundation) |
| **Hetzner Cloud documentation / tutorials** | Terraform and cloud-init patterns | Hetzner docs (see Hetzner copyright on docs) |
| **kube-hetzner / community Hetzner+k3s examples** | Reference for networking and node layout | Various OSS (see linked repos in `docs/`) |
| **Kubernetes SIG / vendor YAML** | metrics-server, HAProxy ingress manifests | Typically Apache-2.0 |
| **Hubs Foundation branding assets** | Logos in `app/ui/public/images/` | Trademarks/branding — not redistributable beyond project branding intent |

See [AI-DISCLOSURE.md](./AI-DISCLOSURE.md) for how these were adapted and transcribed.

---

## 8. HCCE container images (deployed to cluster, not in installer repo)

The installer configures but does not ship Hubs Community Edition container images. Default image references point to Hubs Foundation registries (e.g. `hubsfoundation/reticulum`, `hubsfoundation/hubs`, `hubsfoundation/spoke`). Those images are governed by their own licenses and terms.

---

## 9. Your responsibilities when distributing

If you **redistribute the Docker image** or **fork this repository**:

1. **Keep** `LICENSE`, `THIRD-PARTY-NOTICES.md`, and `AI-DISCLOSURE.md` with the distribution.
2. **Comply** with BUSL-1.1 if you redistribute the Terraform binary (see HashiCorp’s current license FAQ).
3. **Include** Apache-2.0 notices for kubectl/Helm if required by their redistribution terms.
4. **Do not** imply HashiCorp, Hetzner, or Hubs Foundation **endorse** your fork unless you have permission (see footer disclaimer in the UI).
5. **Review** runtime-fetched components (Helm charts, CCM YAML) for license changes when upgrading versions.

---

## 10. Questions

For licensing of **this project’s source code**, see [LICENSE](./LICENSE).

For **AI provenance**, see [AI-DISCLOSURE.md](./AI-DISCLOSURE.md).

For **operational documentation**, see [README.md](./README.md) and `docs/`.

**Last updated:** 2026-08-06
