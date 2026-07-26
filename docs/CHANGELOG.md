# Changelog

## [Unreleased] — 2026-07-26

### Fixed

- Ingress Load Balancer was created with **zero targets**, requiring a manual "attach server"
  step in the Hetzner console on every cluster. k3s ran with `--disable-cloud-controller` but
  without `--kubelet-arg=cloud-provider=external`, which the Hetzner CCM requires — without it
  the CCM never sets `spec.providerID`, so it cannot map Kubernetes nodes to Hetzner servers.
  Verified fixed by a full provisioning run: targets now attach automatically.
- Firewall hardening **destroyed and recreated all three servers**. It re-rendered the whole
  Terraform spec from `templates/` and ran `terraform apply -auto-approve` against it, so any
  template drift since provisioning (`user_data` is ForceNew) came along for the ride.
  Hardening now rewrites only the two firewall variables in the deployed `terraform.tfvars`,
  plans with `-target=hcloud_firewall.open_firewall`, verifies the plan via
  `terraform show -json`, and applies that exact saved plan. Anything other than an in-place
  firewall update aborts.
- Every `terraform apply` on every cluster wanted to replace all three servers. The hcloud
  provider never writes `location` back into state (empty on all 11 instances) while the
  config always sets it, and `location` is ForceNew. Added
  `lifecycle { ignore_changes = [location] }` to the server resources — a server's location
  cannot be changed in place, so it can only ever be realised by an explicit destroy + create.

### Added

- `wait_nodes_initialized()` gate after CCM install — blocks until every node has a
  `hcloud://` providerID, and fails with an actionable message instead of letting later steps
  hang on unschedulable pods (nodes now carry the `uninitialized` taint until the CCM clears it)

### Known Issues

- The pinned `ccm-networks.yaml` v1.23.0 runs with `--allocate-node-cidrs=true
  --cluster-cidr=10.244.0.0/16`, but the cluster uses `10.42.0.0/16` and k3s already allocates
  node pod CIDRs. Does not affect Load Balancer targets. Not yet investigated.
- An instance is frozen at the spec it was rendered with, so template fixes only reach new
  instances. No migration path short of destroy + re-provision.

## [Unreleased] — 2026-07-25

### Fixed

- Workers failing to join the cluster. Two regressions in the cloud-init bootstrap: a
  `curl -f` readiness probe against `/readyz` (returns 401 anonymously, so the wait loop
  never exited) and an `ip route add ... scope link` for the private network (overrode
  Hetzner's gateway route and blackholed peer traffic). See
  [CLUSTER-BOOTSTRAP-POSTMORTEM.md](CLUSTER-BOOTSTRAP-POSTMORTEM.md).
- Pipeline no longer aborts on transient `ssh_unreachable` while a VM is still booting, or on
  `cloud-init: status: error` when `runcmd` is still making progress.

### Added

- Private NIC auto-detection so `--flannel-iface` survives interface renames across images
- `kernel.apparmor_restrict_unprivileged_userns=0` for Ubuntu 24.04 containerd compatibility
- Bootstrap stage markers surfaced in cluster diagnostics
- 3-attempt k3s join retry so a lost etcd race self-heals

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
