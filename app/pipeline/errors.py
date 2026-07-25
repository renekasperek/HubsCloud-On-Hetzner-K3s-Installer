from __future__ import annotations


def format_terraform_error(stderr: str, stdout: str) -> str:
    text = (stderr or "") + "\n" + (stdout or "")
    for line in text.splitlines():
        lower = line.lower()
        if "invalid server type" in lower or "server type" in lower and "not found" in lower:
            return line.strip()
        if "error:" in lower:
            return line.strip()
    snippet = text.strip()[-2000:]
    return snippet or "Terraform failed (see logs)"


def classify_pipeline_error(message: str) -> str | None:
    lower = message.lower()
    if "server type" in lower or "invalid server type" in lower or "server_types" in lower:
        return "server_types"
    if "hetzner" in lower and ("401" in lower or "403" in lower or "token" in lower):
        return "credentials"
    if "firewall" in lower or "hardened firewall" in lower:
        return "firewall"
    if "destroy" in lower or "terraform destroy" in lower:
        return "destroy"
    if "hetzner is not clean" in lower or "hcce resources still exist" in lower:
        return "destroy"
    if any(
        token in lower
        for token in (
            "3 nodes",
            "cluster join",
            "cloud-init",
            "private network",
            "private nic",
            "enp7s0",
            "workers may still be running",
        )
    ):
        return "cluster_join"
    return None
