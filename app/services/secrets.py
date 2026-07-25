from __future__ import annotations

import json
import secrets
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from schemas.models import InstanceSpec


def generate_secrets() -> dict[str, str]:
    perms_key, pgrst_jwt_secret = generate_rsa_material()
    return {
        "k3s_token": secrets.token_hex(32),
        "db_password": secrets.token_urlsafe(24),
        "node_cookie": secrets.token_hex(16),
        "guardian_key": secrets.token_hex(24),
        "phx_key": secrets.token_hex(24),
        "admin_password": secrets.token_urlsafe(16),
        "perms_key": perms_key,
        "pgrst_jwt_secret": pgrst_jwt_secret,
    }


def generate_rsa_material() -> tuple[str, str]:
    """Return (PERMS_KEY, PGRST_JWT_SECRET) in the same single-line format as k3s-setup/hcce/hcce.yaml."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    # Production hcce.yaml stores PEM as one line with \\n (two chars: backslash + backslash + n).
    # Turkey substitutes this into config.toml; a single \n would become a real newline and break TOML.
    escaped = private_pem.replace("\n", "\\\\n")
    public_numbers = key.public_key().public_numbers()
    n = public_numbers.n
    e = public_numbers.e
    import base64

    def b64url_uint(val: int) -> str:
        b = val.to_bytes((val.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(b).decode().rstrip("=")

    jwt_secret = json.dumps({"kty": "RSA", "n": b64url_uint(n), "e": b64url_uint(e)})
    return escaped, jwt_secret


def write_ssh_keypair(instance_dir: Path) -> tuple[str, str]:
    ssh_dir = instance_dir / "ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    key_path = ssh_dir / "id_ed25519"
    pub_path = ssh_dir / "id_ed25519.pub"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", "", "-q"],
        check=True,
    )
    private_key = key_path.read_text()
    public_key = pub_path.read_text().strip()
    key_path.chmod(0o600)
    return public_key, private_key
