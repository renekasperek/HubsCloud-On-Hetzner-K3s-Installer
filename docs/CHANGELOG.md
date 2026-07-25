# Changelog

## [1.0.0] — 2026-07-24

### App

- Added FastAPI installer with Create New Instance wizard (Harbor Desk UI)
- Added pipeline: Terraform → k3s → CCM/CSI → HAProxy → cert-manager → curated HCCE
- Added live cluster resource polling and secrets ZIP download
- Manage Existing stub page

### Templates

- Added redacted Terraform multi-node layout with size/location variables
- Added HAProxy, cert-manager issuer, CCM/CSI secrets, metrics-server, curated `hcce.yaml.j2` with pgsql-backup

### Redacted

- All production credentials removed from templates; placeholders only
