from __future__ import annotations

import subprocess
from pathlib import Path


def ssh_args(key: Path) -> list[str]:
    return [
        "-i",
        str(key),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=20",
        "-o",
        "CheckHostIP=no",
        "-o",
        "LogLevel=ERROR",
    ]


def ssh_err_snippet(result: subprocess.CompletedProcess) -> str:
    text = (result.stderr or result.stdout or "unknown error").strip().replace("\n", " | ")
    return text[:240]


def ssh_run(key: Path, host: str, user: str, remote_cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    result = subprocess.run(
        ["ssh", *ssh_args(key), f"{user}@{host}", remote_cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()


def ssh_auth_ok(key: Path, host: str, user: str, *, timeout: int = 30) -> tuple[bool, str]:
    result = subprocess.run(
        ["ssh", *ssh_args(key), f"{user}@{host}", "echo ok"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode == 0:
        return True, ""
    return False, ssh_err_snippet(result)


def ssh_cat_file(key: Path, host: str, user: str, remote_path: str, *, timeout: int = 90) -> tuple[bool, str, str]:
    remote = (
        f"if [ ! -e '{remote_path}' ]; then echo 'not found' >&2; exit 2; "
        f"elif [ ! -r '{remote_path}' ]; then echo 'not readable' >&2; exit 3; "
        f"else cat '{remote_path}'; fi"
    )
    result = subprocess.run(
        ["ssh", *ssh_args(key), f"{user}@{host}", remote],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode == 0 and len(result.stdout) > 50:
        return True, result.stdout, ""
    if result.returncode == 2:
        return False, "", "file not found yet"
    if result.returncode == 3:
        return False, "", "file not readable"
    err = (result.stderr or result.stdout or "").strip()
    if not err:
        err = f"ssh exit {result.returncode}"
    return False, "", err[:240]


def ssh_diagnose(key: Path, host: str) -> tuple[bool, str | None]:
    """Return (reachable, issue_code). Distinguishes key mismatch from other SSH failures."""
    last_err = ""
    for user in ("cluster", "root"):
        code, out, err = ssh_run(key, host, user, "echo ok", timeout=25)
        if code == 0 and out == "ok":
            return True, None
        combined = f"{err} {out}".lower()
        last_err = (err or out or f"exit {code}").strip()
        if "permission denied" in combined or "publickey" in combined:
            return False, "ssh_key_mismatch"
    if "connection timed out" in last_err.lower() or "no route" in last_err.lower():
        return False, "ssh_unreachable"
    return False, "ssh_unreachable"


def ssh_probe(key: Path, host: str, remote_cmd: str) -> tuple[bool, str]:
    for user in ("cluster", "root"):
        code, out, err = ssh_run(key, host, user, remote_cmd, timeout=45)
        if code == 0:
            return True, out
        if "permission denied" not in (err or "").lower():
            return False, err or out or f"exit {code}"
    return False, "SSH unreachable"
