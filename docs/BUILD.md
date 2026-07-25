# Hubs Installer — build notes

## Layout

- `app/` — FastAPI + React (Harbor Desk UI)
- `templates/` — redacted Terraform, K8s platform, curated HCCE (`hcce.yaml.j2`)
- Dockerfile `COPY templates/ → /opt/templates`
- Runtime data: `/data` (compose volume `./data`)

## Templates provenance

Initial templates were derived from this monorepo (read-only):

- `terraform/` → `templates/terraform/`
- `k3s-setup/haproxy/`, `cluster-issuer`, metrics-server, storage class → `templates/k8s/`
- `k3s-setup/hcce/hcce.yaml` → redacted `templates/hcce/hcce.yaml.j2` (pgsql-backup preserved)

The `hubs-cloud/` submodule is **not** used. No upstream `gen-hcce`.

## Secrets firewall

Never commit: live tokens, production passwords, private keys, kubeconfigs, tfstate.

Runtime secrets live only under `./data/` (gitignored).

## Placeholders

See [templates/README.md](../templates/README.md).

## Build & run

```bash
cd installer
docker compose up --build
# open http://127.0.0.1:8080
```

Copy-out: `cp -R installer ~/elsewhere && cd ~/elsewhere && docker compose up --build`

## UI

Single-process: uvicorn serves API + static SPA from `app/ui/dist`.

## Docker build troubleshooting

### `esbuild` / `ETXTBSY` during `npm install`

On Docker Desktop for Mac, the esbuild postinstall script can fail with:

```text
Error: spawnSync .../node_modules/esbuild/bin/esbuild ETXTBSY
```

This is a known Docker Desktop + Linux kernel race when a native binary is written and executed in the same step. The Dockerfile avoids it by running `npm ci --ignore-scripts` and only attempting the esbuild native install as a best-effort step.

If you still hit this on an older copy of the installer:

1. Pull the latest `Dockerfile` (or apply the same `npm ci --ignore-scripts` change).
2. Retry: `docker compose build --no-cache`.
3. In Docker Desktop → Settings → General, try disabling **Use Rosetta for x86/amd64 emulation on Apple Silicon** if enabled, then rebuild.

## Failure handling (v1)

On pipeline failure: fix the issue, return to wizard review, re-run **Create cluster**. No partial resume.
