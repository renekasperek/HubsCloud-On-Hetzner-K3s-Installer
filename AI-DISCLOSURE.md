# AI Usage Disclosure

This document describes how generative AI was used to create the **Hubs Cloud on Hetzner K3s Installer** ([splexit/HubsCloud-On-Hetzner-K3s-Installer](https://github.com/splexit/HubsCloud-On-Hetzner-K3s-Installer)).

It follows the disclosure expectations in the Hubs Foundation [AI Usage Policy](https://github.com/Hubs-Foundation/policies-procedures-guidelines-public/pull/17) (Level 3: AI used for integrated project content).

This repository is **not** submitted as a pull request to Hubs Foundation repositories. It is published independently under [MPL 2.0](./LICENSE), the same license text used by [Hubs Foundation hubs](https://github.com/Hubs-Foundation/hubs/blob/master/LICENSE).

---

## Honest summary

**Most of this repository is AI-generated output with human direction, not human-written code that was lightly assisted by AI.**

The maintainer's role has been to:

- Provide requirements, corrections, and source material
- Manually edit infrastructure manifests before templating (see below)
- Run the installer against real Hetzner clusters and report what works or breaks
- Accept or reject agent output — often accepting it with little or no line-by-line editing

This disclosure file itself was written by the AI agent from the maintainer's description and was **not** manually rewritten before publication.

---

## AI tools used

| Tool | Role |
|------|------|
| **Cursor IDE** | Primary development environment |
| **Cursor Agent** | Code generation, refactoring, documentation, transcription |

Model names and versions vary by session. Specific model identifiers and prompts were **not** systematically retained.

---

## What was created how

### Templates (`templates/`) — partial human origin

These are the main area where a human edited files **before** AI involvement:

1. **Terraform** (`templates/terraform/`)  
   - Started from **Hetzner Cloud tutorial / reference material**.  
   - A human manually edited server definitions, networking, firewall behaviour, and cloud-init for master / web / WebRTC workers.  
   - An AI agent then transcribed those edits into Jinja2 templates (`.j2`, placeholder wiring).

2. **HCCE manifest** (`templates/hcce/hcce.yaml.j2`)  
   - Started from the **original `hcce.yaml` provided by Hubs Foundation**.  
   - A human manually edited it for this Hetzner + external HAProxy + k3s layout.  
   - An AI agent transcribed the edited YAML into a Jinja2 template.

3. **Platform Kubernetes manifests** (`templates/k8s/`)  
   - Sourced from upstream or reference manifests, manually adapted, then transcribed or refactored into templates by the agent.

4. **Scripts** (`templates/scripts/`)  
   - Adapted from existing k3s/HCCE setup material; templating and integration by the agent.

Even here, the **current template files in the repo** are agent output. The human contribution is the edited source material and decisions that preceded transcription — not necessarily a full manual review of every line in the committed templates.

### Backend (`app/` — Python)

**Fully AI-generated** from maintainer prompts and iterative agent sessions.

Includes the FastAPI API, provisioning/destroy pipeline, Hetzner integration, secrets handling, rendering, repair logic, and diagnostics.

### Frontend (`app/ui/` — React)

**Fully AI-generated** from maintainer prompts (UX direction, branding assets, copy requests).

Includes the wizard, progress UI, docs viewer, and styling.

### Automation, docs, and this file

**Fully AI-generated**, including:

- `Dockerfile`, `docker-compose.yml`
- `README.md`, `docs/`, `templates/README.md`
- **`AI-DISCLOSURE.md`** (this document)

---

## What the maintainer actually did

| Activity | Extent |
|----------|--------|
| Directed the agent (features, fixes, branding, wording) | Substantial |
| Manually edited Terraform / HCCE YAML before templating | Yes — templates section only |
| Line-by-line review of all AI-generated code | **No** — not claimed |
| Ran installer against Hetzner and iterated on failures | Yes |
| Rewrote AI output before commit | Often minimal or none |

---

## Third-party sources (not AI-generated)

| Source | Used for |
|--------|----------|
| Hubs Foundation `hcce.yaml` | Base HCCE manifest (human-adapted before templating) |
| Hetzner Cloud documentation and tutorials | Terraform / cloud-init patterns |
| Upstream k8s manifests | HAProxy, cert-manager, CSI, metrics-server, etc. |
| Branding assets in `app/ui/public/images/` | Hubs / Hetzner logos (not AI-generated) |
| [MPL 2.0](https://www.mozilla.org/MPL/2.0/) | License text (same as Hubs Foundation hubs) |

---

## Copyright and policy note

The Hubs Foundation AI policy discourages accepting submissions that are **significantly or fully AI-generated without human rework** — partly because unmodified model output may not carry clear copyright under the project's license.

This repository is published **outside** that contribution path. The maintainer publishes it independently and accepts that:

- Much of the codebase is agent output they have **directed but not comprehensively rewritten**
- Templates incorporate human-edited infrastructure manifests as their primary non-AI input
- Operational use on Hetzner is the main practical validation, not a formal code audit

If you rely on this installer, treat it accordingly: review security-sensitive paths yourself, test in a non-production environment first, and do not assume every line has been human-verified.

---

## Future changes

If this repository accepts outside contributions, those contributors should disclose AI use and follow the Hubs Foundation [AI Usage Policy](https://github.com/Hubs-Foundation/policies-procedures-guidelines-public/pull/17) as a reference standard.

---

## Summary table

| Area | Human work | AI work |
|------|------------|---------|
| Terraform & cloud-init templates | Manual edits from Hetzner tutorial lineage | Transcription to Jinja2 + repo maintenance |
| HCCE & k8s templates | Manual edits from Hubs Foundation hcce.yaml / upstream YAML | Transcription / refactor to `.j2` |
| Python backend | Direction, testing feedback | **Fully generated** |
| React UI | Direction, assets, copy requests | **Fully generated** |
| Docker, README, docs, this disclosure | Direction | **Fully generated** |

**Last updated:** 2026-08-06
