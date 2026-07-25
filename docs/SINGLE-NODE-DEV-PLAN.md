# Single-node dev vs multi-node HA — deferred plan

Status: **saved for later** (not scheduled).  
Context: wizard choice between current 3-node HA cluster and a cheaper 1-node developer cluster.

---

## Problem statement

Multi-node exists mainly to avoid **port conflicts** and resource contention, not only for HA.

On a **single host**, these compete for the same ports:

| Consumer | Port | Binding |
|----------|------|---------|
| HAProxy ingress | 4443 | `--https-bind-port=4443` + LB `targetPort: 4443` |
| HAProxy (TURN passthrough) | 5349 | containerPort + LB service |
| k3s **svclb** (ServiceLB) | 4443, 5349 | host bindings on node running LB pod |
| **dialog** | 4443 | `hostNetwork: true` + `hostPort: 4443` |
| **coturn** | 5349 | `hostNetwork: true` + `hostPort: 5349` |

**Current multi-node split:**

- **Master** (`hcce-master-db`): DB, Reticulum, HAProxy, svclb pinned via `lbpool=master-only`
- **WebRTC worker** (`hcce-webrtc-worker`): dialog + coturn with hostNetwork/hostPort
- **Web worker** (`hcce-web-worker`): Hubs, Spoke, image processing

Terraform-only “1 server instead of 3” without template changes will likely leave dialog/coturn **Pending** (same class of issue as svclb blocking WebRTC ports).

---

## Product axis (separate from cluster_size)

`cluster_size` (small/medium/large) only scales **CPX sizes across three nodes**.

Add a new field, e.g.:

```text
deployment_topology: multi_node | single_node
```

- **multi_node** — today’s default (production HA)
- **single_node** — developer / cheap sandbox

---

## Single-node strategies

### Strategy A — Dev networking profile (recommended for “developer cluster”)

- Remove `hostNetwork` / `hostPort` on dialog/coturn
- Route via cluster Services + HAProxy (precedent: `old.hcce-ref/hcce.yaml`)
- dialog: normal Deployment + Service (4443)
- coturn: normal Deployment + Service (5349)
- HAProxy TCP: `5349 → hcce/coturn:5349`; dialog via **ingress** on `stream.{hub}` (already used in prod)
- No `nodeSelector` split — everything on one node
- k3s install with **`--node-taint=`** so workloads schedule on control-plane (see root `Readme.md`)

**Pros:** No host port war with HAProxy/svclb on one machine.  
**Cons:** WebRTC path differs from production; TURN/UDP through LB can be fiddly. OK for dev, not a prod substitute.

### Strategy B — Keep hostNetwork on single node

Must choose **one** owner of 4443/5349 on the host (HAProxy **or** dialog/coturn, not both).

Likely: LB only 80/443; expose WebRTC on node public IP or non-standard ports → more Reticulum/CSP config (`janus_port`, `public_tls_ports`).

**Pros:** Closer to Mozilla hostNetwork design.  
**Cons:** Split URLs, easy to misconfigure; poor fit for “it just works” installer.

**Recommendation:** Strategy A for dev; keep current multi-node for HA/production.

---

## What must change (beyond Terraform)

| Area | Multi-node (today) | Single-node dev |
|------|-------------------|-----------------|
| Terraform | 3× `hcloud_server` | 1× server; optional simplify placement group |
| cloud-init | master + 2 workers | single server, `--node-taint=`, no worker join |
| Labels | 3× `workload-type` | all on one node, or drop nodeSelectors |
| svclb | master-only pool | less critical without hostPorts; still document |
| `hcce.yaml.j2` | nodeSelectors + hostNetwork | Jinja `{% if topology == 'ha' %}` branches |
| HAProxy | LB 80/443/4443/5349 | dev profile: possibly 80/443 only on LB |
| Pipeline | `plan_labels()` + `plan_svclb_labels()` | conditional for 1 node |
| Wizard | 3 server type dropdowns | one server type + cost estimate |
| Health checks | expects 3 nodes, svclb on workers = fail | profile-aware |
| Presets/pricing | sum 3 servers | 1 server + LB + volume |

---

## Effort estimate

| Work package | Effort | Risk |
|--------------|--------|------|
| Terraform single-node + conditionals | 1–2 days | Low |
| Jinja branches (hcce + haproxy) | 2–3 days | Medium |
| Pipeline, labels, wizard, spec model | 1–2 days | Low |
| Health/monitoring profile-aware | 0.5 day | Low |
| WebRTC E2E (rooms, audio, TURN) | 2–5 days | **High** |
| Docs | 0.5 day | Low |

**Total:** ~1–2 weeks credible v1; 2–3 weeks if dev must match prod WebRTC closely.

---

## Decisions before building

1. **May dev differ from prod?** (If no → much more work.)
2. **Minimum server size** for single-node (Postgres + Reticulum + Hubs + HAProxy + dialog + coturn is heavy; e.g. CPX42 floor + UI warning).
3. **Hetzner LB on dev** — fixed LB cost; optional “no LB” branch (NodePort / node IP) for cheapest dev.
4. **Upgrade path** — single → multi is **new cluster + migrate**, not in-place toggle.
5. **Test matrix** — two topologies × certs × DNS × WebRTC.

---

## Suggested first spike (when revisiting)

Do **not** start with Terraform.

1. Render a **single-node dev** manifest variant (Strategy A) from templates.
2. Apply to a throwaway CPX32/42.
3. Validate: HAProxy + dialog/coturn + room join without hostPorts.
4. Only then add `deployment_topology` to wizard + conditional Terraform.

---

## References in repo

- Multi-node rationale: `MULTINODE-DEPLOYMENT-GUIDE.md`
- svclb fix: `installer/templates/scripts/configure-node-labels.sh`, `plan_svclb_labels()` in `app/renderers/__init__.py`
- Single-node k3s taints: root `Readme.md` (control-plane scheduling)
- Non-hostNetwork HCCE reference: `old.hcce-ref/hcce.yaml`
- Port conflict history: `DEVLOG.md`
