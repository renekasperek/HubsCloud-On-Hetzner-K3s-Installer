# Next Steps — Deferred Hardening Work

Work identified but **deliberately not included** in the current release. Pick this up at the
next version bump.

Items 1–4 came out of a comparison against
[terraform-hcloud-kube-hetzner](https://github.com/kube-hetzner/terraform-hcloud-kube-hetzner),
the reference Terraform module for k3s on Hetzner. Our architecture is sound and there is no
reason to switch to it — it is a Terraform module, we are an application with a wizard, an API
and lifecycle operations. Treat it as a checklist of already-solved edge cases, not as a
replacement.

| # | Item | Why it matters | Effort |
| --- | --- | --- | --- |
| ~~1~~ | ~~Pin the k3s version~~ | **Done 2026-07-26** — see [below](#1--pin-the-k3s-version-done) | — |
| 2 | [etcd snapshots](#2--etcd-snapshots) | Cluster state is currently unrecoverable | Small |
| 3 | [Restrict API and SSH source ranges](#3--restrict-api-and-ssh-source-ranges) | "Hardened" firewall exposes 6443 to the internet | Small, needs a decision |
| 4 | [OS patching policy](#4--os-patching-policy) | Security patches never land | Medium, needs a decision |
| 5 | [Encrypt node-to-node traffic](#5--optional-encrypt-node-to-node-traffic) | Hetzner private networks are isolated, not encrypted | Small |

---

## 1 — Pin the k3s version (DONE)

> **Resolved 2026-07-26.** Pinned to **`v1.36.2+k3s1`** in all six install sites. Kept here
> for context, and because the *remaining* work — making the version a spec field — is still
> open (see [Follow-up](#follow-up-still-open) at the end of this section).

**Problem.** k3s was installed unpinned, so every provisioning run took whatever was latest at
that moment:

```bash
curl -sfL https://get.k3s.io | sh -
```

**Why it matters.** Two clusters built a week apart get different k3s versions, and an upstream
release can break bootstrap with no change on our side — a real risk given how much of this
project's history is bootstrap debugging. The sharper problem is **version skew**:
`app/pipeline/cluster_repair.py` reinstalls k3s on a broken node, so a repaired worker can join
an older master running a newer k3s, inside the same etcd cluster.

kube-hetzner avoids this deliberately — addon and k3s versions use "reviewed defaults rather
than floating upstream latest versions, reducing surprise mid-apply version bumps."

**What was done.** `INSTALL_K3S_VERSION=v1.36.2+k3s1` set in all six places that install k3s:

- `templates/terraform/cloud-init-master.yaml`
- `templates/terraform/cloud-init-webrtc-worker.yaml`
- `templates/terraform/cloud-init-web-worker.yaml`
- the three entries in `K3S_INSTALL` in `app/pipeline/cluster_repair.py`, via the module
  constant `K3S_VERSION` so the repair path cannot drift from itself

**Why this version.** `v1.36.2+k3s1` is the version observed running on the cluster that was
verified healthy end to end on 2026-07-26 — 3/3 nodes `Ready`, all pods `Running`, Load
Balancer targets attaching automatically. It is a proven-good build, not merely the latest.

**Why an exact pin rather than a channel.** `INSTALL_K3S_CHANNEL=v1.36` would track the latest
patch in the 1.36 line, which reintroduces both problems: two clusters built weeks apart get
different builds, and a repaired node can pick up a newer patch than the master it joins.

**Verified.** All three templates render through `templatefile()`, parse as YAML, and carry the
pin; the three repair commands render with the same version. `grep` confirms no unpinned
`get.k3s.io` install remains anywhere in `templates/` or `app/`.

**On upgrading later.** k3s is not upgraded by changing this pin on a running cluster — the
value only takes effect at first boot. Moving an existing cluster to a new k3s version is a
separate operation (see item 4's rolling-reboot discussion, or `system-upgrade-controller`).

### Follow-up, still open

The version is hardcoded in six places. A drifting edit is now the main risk, and the comment
above `K3S_VERSION` in `cluster_repair.py` warns about it. The durable fix is to make it a spec
field with a validated default, rendered into the cloud-init templates as a Terraform variable
— which would also let the wizard surface it. Deferred: it touches `schemas/`, `renderers/`,
`terraform.tfvars.j2` and `main.tf`, which is more than this release should carry.

---

## 2 — etcd snapshots

**Problem.** Nothing configures etcd snapshots.

**Why it matters.** All three nodes run as k3s `server`, so all three carry etcd. Quorum is 2 —
lose two nodes and the cluster is **unrecoverable**, because there is no snapshot to restore
from. The existing Postgres backup guardian covers application data, not cluster state.
kube-hetzner ships etcd S3 backups with a documented restore workflow.

**Fix.** k3s supports this natively on the server command line:

```
--etcd-snapshot-schedule-cron="0 */6 * * *"
--etcd-snapshot-retention=14
```

Optionally ship snapshots off-box with `--etcd-s3` against Hetzner Object Storage, so a full
region loss is survivable. Local snapshots alone do not protect against losing the servers.

**Verify.** After provisioning, confirm snapshots appear under
`/var/lib/rancher/k3s/server/db/snapshots/`, and do a restore rehearsal at least once.

---

## 3 — Restrict API and SSH source ranges

**Problem.** The hardened firewall opens the Kubernetes API to the entire internet.
`templates/terraform/main.tf`:

```hcl
for port in ["80", "443", "6443", "4443", "5349", "31621", "32471"] :
  source_ips = ["0.0.0.0/0", "::/0"]
```

Port **6443** is the kube-apiserver. Port **22** is likewise `0.0.0.0/0` when
`firewall_allow_ssh` is set.

**Why it matters.** This is the item to take most seriously — not because the gap is the
largest, but because the feature is *called* hardening, so it reads as handled. kube-hetzner
exposes exactly these two as `firewall_kube_api_source` and `firewall_ssh_source`, allowlisted
by default.

Note 80, 443, 4443 (dialog) and 5349 (turn) are legitimately public — this is only about 6443
and 22.

**Fix.** Add two spec fields, e.g. `firewall_kube_api_source` and `firewall_ssh_source`
(`list(string)`), plumb them into the firewall rules, and default to an allowlist rather than
`0.0.0.0/0`.

**Decision needed before implementing:** which source ranges. The installer itself needs 6443
reachable to run `kubectl` during provisioning, so if the installer runs from a dynamic IP,
the allowlist has to account for that. Worth deciding whether the installer should reach the
API over the private network or a fixed egress IP instead.

---

## 4 — OS patching policy

**Problem.** No `unattended-upgrades`, no reboot coordination, and SSH is hardened after
provisioning. Security patches will not land unless someone applies them by hand.

**Why it matters.** kube-hetzner sidesteps this architecturally with an immutable OS
(openSUSE Leap Micro, "most of the OS is read-only—hardened by design") plus transactional
updates, and uses Kured for "HA-aware OS reboots". We are on Ubuntu 24.04, so we need an
explicit policy instead.

**Options, cheapest first.**

1. Enable `unattended-upgrades` for security updates only, no automatic reboot. Kernel/libc
   updates then sit pending until a manual reboot.
2. The above, plus a documented rolling-reboot runbook (drain → reboot → uncordon, one node
   at a time, never breaking etcd quorum).
3. Deploy Kured for automatic HA-aware reboots. Closest to kube-hetzner; most moving parts.

**Decision needed:** how much unattended change is acceptable on a cluster running Hubs. Option
1 alone is a large improvement over the current state and carries almost no risk.

---

## 5 — Optional: encrypt node-to-node traffic

**Problem.** flannel runs its default vxlan backend, unencrypted.

**Why it matters.** Hetzner private networks are *isolated* but **not encrypted**. All pod
traffic — Hubs media, signalling, database connections between nodes — crosses that link in
cleartext. kube-hetzner offers WireGuard for exactly this case.

**Fix.** One k3s flag on every node: `--flannel-backend=wireguard-native`.

**Caveat.** Must be set at cluster creation; changing the flannel backend on a running cluster
is not a supported in-place operation. So it belongs in the same release as any other
cloud-init change, and needs a fresh cluster to validate.

---

## Already logged elsewhere

Recorded during the 2026-07-25/26 work, repeated here so the version bump has one list to
work from. See `CLUSTER-BOOTSTRAP-POSTMORTEM.md` for full context.

- **CCM manifest CIDR mismatch — investigated 2026-07-26, low priority.** The pinned
  `ccm-networks.yaml` is the upstream Helm chart rendered with *default* values, so it carries
  `--cluster-cidr=10.244.0.0/16` while our cluster uses `10.42.0.0/16`. The chart states
  `networking.clusterCIDR` *"must match the PodCIDR subnet your cluster has been configured
  with"*.
  **Not currently harmful:** the route controller programs Hetzner network routes from each
  node's `spec.podCIDR`, and flannel VXLAN encapsulates pod traffic without relying on them.
  It does **not** allocate pod CIDRs — that is kube-controller-manager's job — so there is no
  competing allocator (an earlier note claiming otherwise was wrong).
  **Fix when convenient:** set the CIDR to `10.42.0.0/16`, either by installing the CCM via its
  Helm chart with `networking.clusterCIDR` (consistent with how CSI is already installed) or by
  patching the flag. This is what kube-hetzner does — it wires `networking.clusterCIDR` from its
  `cluster_ipv4_cidr` variable. Keep the **networks** variant: Load Balancer private-IP
  attachment depends on the CCM knowing the network.
- **No spec migration path.** An instance is frozen at the spec it was rendered with, so
  template fixes only reach new instances. The clean answer is an explicit "reconcile instance
  spec" API operation that re-renders, plans, and surfaces the plan for approval instead of
  applying it — reusing the plan-gate machinery in `app/pipeline/firewall.py`.
- **Provider upgrade unvalidated against live state.** hcloud provider was bumped 1.50.0 →
  1.67.0 with schema and `validate` checks only. Not yet exercised against a real cluster.
  Watch: servers create normally, `terraform plan` is clean afterwards, hardening still
  produces `1 to change`.
- **`ignore_changes = [location]` is load-bearing.** Verified still required at provider
  1.67.0. Do not remove it on the assumption that a provider upgrade fixed the state drift.
