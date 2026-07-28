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

- **Volume inventory and reattach** — pipeline saves `volumes-inventory.json` (PVC → Hetzner volume ID)
  after HCCE deploy and on destroy; wizard step *Machines & SSH* offers reattach when saved volumes
  exist; reprovision applies `hcce-static-pvs.yaml` before HCCE PVCs. See `docs/VOLUME-RECOVERY.md`.
- `wait_nodes_initialized()` gate after CCM install — blocks until every node has a
  `hcloud://` providerID, and fails with an actionable message instead of letting later steps
  hang on unschedulable pods (nodes now carry the `uninitialized` taint until the CCM clears it)

### Changed

- **k3s is now pinned to `v1.36.2+k3s1`** instead of installing whatever `get.k3s.io` serves at
  provisioning time. Applied to all six install sites — the three cloud-init templates and the
  three `K3S_INSTALL` commands in `app/pipeline/cluster_repair.py` (via a `K3S_VERSION`
  constant). This makes provisioning reproducible and, more importantly, removes a version-skew
  hazard: the repair path reinstalls k3s, so an unpinned repaired node could join an older
  master running a newer k3s inside the same etcd cluster. `v1.36.2+k3s1` is the build verified
  healthy end to end on 2026-07-26.
- hcloud Terraform provider **1.50.0 → 1.67.0** (16 minor versions; latest as of 2026-07-24).
  Includes the 1.61.0 fix *"apply_to update removes firewall from state when target resource is
  not found"*, which is in the firewall path. Pinned exactly rather than with `~>`, because
  `.terraform.lock.hcl` is not copied into per-instance terraform dirs — a range would let
  different clusters build with different, untested provider versions.
  Verified: all six resource types we use are present, and every `hcloud_server` attribute we
  set still exists. `datacenter` is deprecated but **not** yet removed, and we never used it.
  Note: the upgrade does **not** fix the `location` state drift — `ignore_changes = [location]`
  remains load-bearing. Not yet exercised against a live cluster.

### Known Issues

- The pinned `ccm-networks.yaml` v1.23.0 is the upstream Helm chart rendered with default
  values, so it carries `--cluster-cidr=10.244.0.0/16` while the cluster uses `10.42.0.0/16`.
  Cosmetic in the current setup — flannel VXLAN does not rely on the routes the CCM programs,
  and the CCM does not allocate pod CIDRs. Should be set to `10.42.0.0/16` when convenient.
- An instance is frozen at the spec it was rendered with, so template fixes only reach new
  instances. No migration path short of destroy + re-provision.
- Deferred hardening work is tracked in [NEXT-STEPS.md](NEXT-STEPS.md) — k3s version pinning,
  etcd snapshots, restricting the kube-API/SSH firewall source ranges, and an OS patching
  policy. To be addressed at the next version bump.

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
