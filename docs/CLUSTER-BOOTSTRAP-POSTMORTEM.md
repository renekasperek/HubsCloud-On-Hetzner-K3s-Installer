# Cluster Bootstrap & Post-Provision Postmortem

**Dates:** 2026-07-25 → 2026-07-26
**Environment:** Hetzner Cloud, Ubuntu 24.04.4 LTS, kernel 6.8.0-124, k3s v1.36.2+k3s1,
hcloud CCM v1.23.0, hcloud Terraform provider 1.50.0

Three separate defects, found in sequence:

| # | Defect | Status |
| --- | --- | --- |
| [1](#part-1--workers-fail-to-join) | Workers never join the cluster | Fixed, verified |
| [2](#part-2--load-balancer-created-with-zero-targets) | Ingress Load Balancer created with 0 targets, attached by hand | Fixed, verified 2026-07-26 |
| [3](#part-3--post-provision-applies-rebuilt-the-cluster) | Firewall hardening destroyed and recreated all three servers | Fixed |

---

# Part 1 — Workers Fail to Join

**Reference instance:** `5427d9c4-9922-4091-aa86-b257ba538d23`
**Outcome:** 3/3 nodes `Ready`, all pods `Running`

## Symptom

Master bootstrapped cleanly every run (`stage=done`, `k3s=active`). Both workers hung
indefinitely at `wait-master-api`, or reached `k3s-install` and crash-looped. The pipeline
reported `Cluster join failed during node bootstrap`.

## Root Causes

Two were **self-inflicted regressions** introduced while debugging. One was environmental.

### 1. `curl -f` against an auth-gated endpoint (regression)

The worker readiness check was changed from the original:

```bash
curl -k -s  --connect-timeout 5 https://10.0.1.1:6443/version    # original — worked
curl -k -sf --connect-timeout 5 https://10.0.1.1:6443/readyz     # regression — hangs forever
```

`-f` makes curl exit non-zero on **any HTTP ≥ 400**. Measured on a live node:

| Endpoint   | Anonymous response |
| ---------- | ------------------ |
| `/readyz`  | **401**            |
| `/version` | **401**            |
| `/cacerts` | **200**            |

The original had no `-f`, so it exited 0 as soon as TCP+TLS connected — it only ever tested
reachability. With `-f`, the loop could never exit against a perfectly healthy master.

### 2. A `scope link` route that blackholed the private network (regression)

An `ensure-private-route` step was added on the theory that Hetzner's `/32` private address
lacked a subnet route. It produced two competing routes:

```
10.0.0.0/16 dev enp7s0 scope link src 10.0.1.1              <- added, metric 0 — WINS
10.0.0.0/16 via 10.0.0.1 dev enp7s0 proto dhcp metric 100   <- Hetzner's, correct
```

Hetzner Cloud networks route peer traffic **through the gateway at `10.0.0.1`** and do not
answer ARP for peer IPs. The `scope link` route told the kernel these peers were on-link, so
it ARPed directly, got no reply, and returned *host unreachable*:

```
level=fatal msg="failed to get CA certs: Get \"https://10.0.1.1:6443/cacerts\":
dial tcp 10.0.1.1:6443: connect: no route to host"
```

Deleting the route on all three nodes restored connectivity immediately. Because k3s runs with
`Restart=always`, the workers then joined on their own with no re-provision.

### 3. Ubuntu 24.04 AppArmor userns restriction (environmental — genuine)

24.04 ships `kernel.apparmor_restrict_unprivileged_userns=1`, which can break containerd's pod
sandbox creation. Setting it to `0` before k3s install is the one legitimate addition to the
original cloud-init.

## Ruled Out — Do Not Re-introduce

Each of these was hypothesised during debugging and **disproven**. They cost several
provisioning cycles.

| Hypothesis | Verdict |
| --- | --- |
| `/32` private address is a bug | **Normal** for Hetzner. Routing comes from the DHCP gateway route. |
| Missing subnet route needs `ip route add` | **Harmful.** See root cause 2. |
| `netplan apply` needed for the private NIC | Unnecessary; the Hetzner datasource already configures it. An added `netplan apply` also hung, freezing bootstrap at `stage=netplan`. |
| Master needs `--node-ip` / `--advertise-address` | Unnecessary. The original omitted both and worked. |
| Hardened firewall blocking etcd peer ports | Not applicable — `firewall_hardened: false` on the failing runs. |
| 1 vCPU / 2 GB too small for the master | Plausible in general (k3s server + etcd is tight at 2 GB) but **not** this failure. |

## Changes Kept

### `templates/terraform/cloud-init-{master,webrtc-worker,web-worker}.yaml`

- **Private NIC auto-detection** (`hcce-detect-private-iface`) — picks the ethernet interface
  that is not the default-route interface, so `--flannel-iface` survives image-level renames
  (`enp7s0` → `ens10` → …) instead of being hardcoded.
- **AppArmor sysctl** before k3s install (root cause 3).
- **Stage markers** (`hcce-stage`) written to `/var/run/hcce-bootstrap.stage` and
  `/var/log/cloud-init-custom.log`, so diagnostics can pinpoint where a node stalled.
- **`hcce-wait-api`** (workers) — probes `/cacerts` and interprets the status code:
  `200` proceed, `401/403` proceed (answering but auth-gated), `000/5xx` keep waiting.
  Bounded at 120 attempts so it can never hang indefinitely.
- **3-attempt join retry** (workers) with `k3s-killall` + `k3s-uninstall` between attempts,
  so a lost etcd race self-heals rather than leaving a half-joined node.
- **Explicit comment** in all three files warning against re-adding a `scope link` route.

Otherwise the templates match the original 1:1 — same k3s flags, same wait-then-install
sequence, same user setup.

### `app/services/node_diagnostics.py`

- `ssh_unreachable` is **no longer fatal** — only `ssh_key_mismatch` is. A booting VM that
  isn't answering SSH yet used to abort the whole pipeline.
- `cloud-init: status: error` is fatal **only** when the bootstrap script also wrote a
  `failed:*` stage marker. Cloud-init reports module-level errors (e.g. a slow apt mirror
  during `package_update`) while `runcmd` is still running fine.
- Log tails widened (40 lines of bootstrap log, 10 of cloud-init output, via `sudo`) so the
  real error reaches the pipeline log instead of being truncated.

## Terraform Templating Gotchas

`templatefile()` runs before cloud-init ever sees these files. Two escapes bit us:

| Intent | Must be written as | Wrong result |
| --- | --- | --- |
| `%{http_code}` in `curl -w` | `%%{http_code}` | `%{` parsed as a Terraform directive → render error |
| `${1:-unknown}` in shell | `$${1:-unknown}` | Terraform tries to resolve the variable |
| `$1` in shell | `$1` | `$$1` renders literally as `$$1` (PID + `1`) — `$$` only collapses before `{` |

## Verification

Render and lint all three templates without provisioning:

```bash
terraform console <<< 'templatefile("templates/terraform/cloud-init-master.yaml", {k3s_token="x", ssh_public_key="x"})'
```

Checks that should pass before any provisioning run:

- all three render through `templatefile()`
- output parses as YAML
- every `write_files` script and inline block passes `bash -n`
- no `ip route add|replace` commands present
- no `curl -f` against `:6443`

Live cluster health:

```bash
ssh cluster@<master-ip> 'sudo k3s kubectl get nodes -o wide'
```

---

# Part 2 — Load Balancer Created With Zero Targets

**Confirmed fixed by a full provisioning run on 2026-07-26.**

## Symptom

After the workloads were deployed, the Hetzner CCM created the ingress Load Balancer and
attached it to the private network — but with **no targets**. Every cluster needed a manual
step: open the Hetzner console and attach the server to the LB by hand.

## Root Cause

k3s was started with `--disable-cloud-controller` but **without**
`--kubelet-arg=cloud-provider=external`. Hetzner's quickstart states the requirement
plainly: *"When creating your cluster you need to provide the `kubelet` option
`--cloud-provider=external`."*

Without it the CCM never initialises the node, so `spec.providerID`
(`hcloud://<server-id>`) is never set. The CCM's service controller uses that field to map
Kubernetes nodes to Hetzner servers. It can still create the LB and attach it to the network
— those need only the API token and the `load-balancer.hetzner.cloud/network` annotation —
but it cannot resolve which servers to add as targets. Hence: LB appears, targets stay at 0.

## Fix

- `--kubelet-arg=cloud-provider=external` added to the k3s command in all three cloud-init
  templates, and to the `K3S_INSTALL` commands in `app/pipeline/cluster_repair.py` so a
  repaired node cannot silently come back without it.
- New `wait_nodes_initialized()` in `app/pipeline/workloads.py`, called immediately after the
  CCM manifest is applied. It blocks until every node has a `providerID` and fails with an
  actionable message otherwise.

The guard exists because the flag has a side effect: nodes now register carrying the
`node.cloudprovider.kubernetes.io/uninitialized:NoSchedule` taint, and **nothing schedules
until the CCM clears it**. Before shipping, two things were verified:

1. The pinned `ccm-networks.yaml` v1.23.0 Deployment tolerates that exact taint, so the CCM
   itself can always schedule — no bootstrap deadlock.
2. Nothing in the pipeline between k3s coming up and the CCM install needs pod scheduling
   (SSH hardening and node labelling are API/SSH operations).

Without the guard, a CCM that fails to start would leave every later step hanging on
unschedulable pods instead of reporting the real problem.

## Open Item — CCM manifest CIDR mismatch

The pinned manifest runs with:

```
--allocate-node-cidrs=true --cluster-cidr=10.244.0.0/16
```

The cluster uses `10.42.0.0/16`. `ccm-networks.yaml` is simply the upstream Helm chart
rendered with default values, and the chart documents the requirement plainly:
`networking.clusterCIDR` (default `10.244.0.0/16`) *"must match the PodCIDR subnet your
cluster has been configured with"*. Ours does not.

**Impact is low, and the cluster is not broken by it.** The CCM route controller programs
routes in the Hetzner network from each node's `spec.podCIDR`. With flannel in VXLAN mode pod
traffic is encapsulated and does not depend on those routes, so pod networking works either
way. The residual effects are that the controller's stale-route reconciliation keys off a
CIDR that matches nothing of ours, and that the configuration would be wrong if native
routing were ever enabled.

**Correction to an earlier note:** this document previously claimed the CCM and k3s both
assign `node.spec.podCIDR`. That was wrong. `--allocate-node-cidrs` on a *cloud* controller
manager only gates the route controller; CIDR allocation is done by kube-controller-manager
(k3s). There is no competing allocator.

**Fix.** Set the cluster CIDR to `10.42.0.0/16` — either install the CCM via its Helm chart
with `networking.clusterCIDR` (consistent with how the CSI driver is already installed) or
patch the flag in the applied manifest. This is what
[kube-hetzner](https://github.com/kube-hetzner/terraform-hcloud-kube-hetzner) does: it wires
`networking.clusterCIDR` from its own `cluster_ipv4_cidr` variable.

Keep the **networks** variant rather than switching to plain `ccm.yaml` — Load Balancer
private-IP attachment depends on the CCM knowing the network, and that is the mechanism
fixed in Part 2.

---

# Part 3 — Post-Provision Applies Rebuilt the Cluster

## Symptom

Firewall hardening on instance `a7aa141b` destroyed and recreated all three servers:

```
Plan: 3 to add, 1 to change, 3 to destroy
hcloud_server.master_node: Destroying... [id=155222597]
```

`1 to change` was the firewall — the actual intent. The other six operations were collateral.

## Root Cause 1 — hardening re-rendered the whole spec

`harden_firewall` called `render_terraform()`, which re-copies `main.tf`, `variables.tf`,
`outputs.tf` **and all three cloud-init YAMLs** from `templates/`, then ran
`terraform apply -auto-approve` against the entire config.

`user_data`, `location`, `image` and `ssh_keys` are all ForceNew on `hcloud_server`. Since
`user_data` comes from the cloud-init templates, any template edit made since provisioning
became a pending server replacement, silently attached to the next apply.

## Root Cause 2 — `location` drift arms every apply

Deeper and worse: the hcloud provider **never writes `location` back into state**. It is `""`
on all three servers of all 11 instances ever created, while the config always sets it. Because
`location` is ForceNew, every plan wants to set it, and therefore to rebuild:

```
+ location = "nbg1" # forces replacement
```

This was not caused by re-rendering. It means *every* full `terraform apply` on *every*
cluster has always wanted to destroy all three servers. Firewall hardening was simply the
first operation to pull the pin.

## Fix

**Scope the operation.** `harden_firewall` no longer re-renders anything. It rewrites only
the two firewall variables in the already-rendered `terraform.tfvars` (rolling back on
failure), then plans with `-target=hcloud_firewall.open_firewall`. Servers depend on the
firewall, not the reverse, so targeting it never pulls them into the plan — which also makes
hardening immune to the `location` drift, and means it works on instances deployed before
any of this was fixed.

**Verify before applying.** The plan is written with `-out`, inspected via
`terraform show -json`, and applied as that saved plan file. The only accepted change is an
in-place `update` to `hcloud_firewall`. A firewall *replacement* is rejected too: the new
firewall would get a new ID, and because the servers are outside the target they would keep
pointing at the old one and silently lose their rules.

**Contain the landmine elsewhere.** `lifecycle { ignore_changes = [location] }` on the three
servers in `main.tf`. This is *not* needed for hardening any more; it protects the paths that
still do a full apply — notably Retry provisioning, where the drift would otherwise replace a
healthy master while recreating the workers.

### Upgrading the provider does not fix this

Checked on 2026-07-26, because the obvious question is whether a newer provider persists
`location` correctly. It does not. Comparing the resource schema of 1.50.0 and 1.67.0:

```
v150 hcloud_server.location: optional=True computed=True
v167 hcloud_server.location: optional=True computed=True
```

`location` is Optional+Computed in both — the provider is *supposed* to read it back from the
API — yet state holds `""`. Nothing in the 1.51 → 1.67 changelog addresses it.

The drift is also not caused by anything we do. Instances that never ran firewall hardening,
whose `terraform.tfvars` set a location at create time, still show an empty value:

```
9d1f6c80 | hardening_runs=0 | tfvars location="fsn1" | state location=''
642dddaf | hardening_runs=0 | tfvars location="nbg1" | state location=''
```

So the provider writes it empty at create and refresh never repairs it. The `ignore_changes`
workaround is therefore load-bearing at every provider version currently available, and must
not be removed on the assumption that an upgrade fixed it. Related long-standing reports,
both closed without resolution: hetznercloud/terraform-provider-hcloud
[#278](https://github.com/hetznercloud/terraform-provider-hcloud/issues/278),
[#471](https://github.com/hetznercloud/terraform-provider-hcloud/issues/471).

## Design Rules

- **A post-provision operation mutates only what the user changed.** A resize legitimately
  replaces a server, because that is what was asked for. A firewall change must never touch a
  server.
- **Blanket `ignore_changes` is the wrong tool.** It cannot distinguish unrequested drift from
  a requested change, so covering `user_data`/`server_type` would have broken the resize path.
  `location` is the exception only because a server's location cannot be changed in place at
  all — Hetzner has no move operation — so it can only ever be realised by an explicit
  destroy + create.
- **Never hand-edit a deployed instance**, its rendered spec, or its cloud resources.
  Everything goes through the API.

## Known Gap

Because an instance is frozen at the spec it was rendered with, template fixes only reach
**new** instances. There is currently no supported way for a running cluster to pick one up
short of destroy + re-provision. That is acceptable for a dev cycle and will not be for
production. The clean answer is an explicit "reconcile instance spec" API operation that
re-renders, plans, and surfaces the plan for approval rather than applying it — reusing the
plan-gate machinery already in `firewall.py`.

## Lessons

1. **Verify hypotheses against a live node before encoding them.** The `scope link` route was
   added on an unverified theory and became the primary failure for several cycles. One
   `ip route get` on a running worker would have caught it immediately.
2. **`curl -f` is wrong for liveness probes** against endpoints that may legitimately return
   401/403. Check the status code explicitly.
3. **Prefer the endpoint the real client uses.** `/cacerts` is what a joining k3s server fetches
   first, so it is a more honest readiness signal than `/readyz`.
4. **When something "worked before", diff against it rather than adding.** Every layer added on
   top of the original cloud-init was either neutral or harmful; only the AppArmor sysctl was
   a genuine environmental fix.
5. **A documented prerequisite is worth more than a plausible theory.** The missing
   `--cloud-provider=external` was stated outright in Hetzner's own quickstart. Reading it
   settled in minutes what guessing had not.
6. **Scope destructive tooling to the thing being changed.** `-target` turned firewall
   hardening from an operation that could rebuild the cluster into one that provably cannot,
   and did so without depending on a template change — so it fixed already-deployed instances
   too.
7. **Inspect the plan, then apply *that* plan.** `terraform plan -out` +
   `terraform show -json` + `terraform apply <planfile>` makes "what was reviewed" and "what
   ran" the same artifact. `-auto-approve` on a freshly generated plan is how six unintended
   operations rode along behind one intended one.
8. **A latent defect can sit armed for a long time.** The `location` drift existed on all 11
   instances from the beginning; nothing surfaced it until an operation finally ran a full
   apply against a live cluster.
