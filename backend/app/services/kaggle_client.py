"""Thin wrapper around the `kaggle` CLI, scoped to a single visitor-supplied
token per call.

Unlike AI_3D_FACTORY's kaggle_generator.py (which reads one fixed credential
from ~/.kaggle for the developer's own account), every call here takes the
token as an explicit argument and writes it to a fresh temporary
KAGGLE_CONFIG_DIR that is deleted immediately after the subprocess call
returns -- the token is never written into this machine's real ~/.kaggle,
never logged, and never lives on disk longer than one subprocess call. The
in-memory job record (see jobs.py) is the only place a token is held between
calls, for the lifetime of that job.
"""
import json
import os
import shutil
import subprocess
import tempfile


class KaggleAuthError(Exception):
    """The provided token was rejected by Kaggle (invalid/expired/malformed)."""


class KaggleCliError(Exception):
    """A kaggle CLI call failed for a reason other than auth."""


def _run_with_token(token, args, timeout=120):
    config_dir = tempfile.mkdtemp(prefix="pf_kaggle_")
    try:
        token_path = os.path.join(config_dir, "access_token")
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(token.strip())
        os.chmod(token_path, 0o600)

        env = dict(os.environ)
        env["KAGGLE_CONFIG_DIR"] = config_dir
        env["PYTHONUTF8"] = "1"

        result = subprocess.run(
            ["python", "-m", "kaggle"] + args,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
        return result
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)


def resolve_username(token):
    """Confirm the token is valid and return the Kaggle username it belongs to.

    Raises KaggleAuthError with no token content in the message if the token
    is missing/invalid -- callers must not echo the raw token back either.
    """
    if not token or not token.strip():
        raise KaggleAuthError("No Kaggle token provided.")

    result = _run_with_token(token, ["config", "view"], timeout=30)
    if result.returncode != 0:
        raise KaggleAuthError(
            "Kaggle rejected this token. Re-check it was copied in full from "
            "kaggle.com/settings -> Create New Token."
        )

    username = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("- username:"):
            username = line.split(":", 1)[1].strip()
    if not username or username in ("None", ""):
        raise KaggleAuthError(
            "Kaggle accepted the request but returned no username -- the "
            "token may be malformed. Try generating a fresh token."
        )
    return username


def push_kernel(token, kernel_dir, accelerator=None):
    """Push a kernel folder (containing kernel-metadata.json + source) using
    the visitor's token. Returns the kernel id ("username/slug") read back
    from kernel-metadata.json in kernel_dir.
    """
    meta_path = os.path.join(kernel_dir, "kernel-metadata.json")
    with open(meta_path, encoding="utf-8") as f:
        kernel_id = json.load(f)["id"]

    args = ["kernels", "push", "-p", kernel_dir]
    if accelerator:
        args += ["--accelerator", accelerator]

    result = _run_with_token(token, args, timeout=60)
    if result.returncode != 0:
        raise KaggleCliError(f"kernel push failed: {result.stderr.strip() or result.stdout.strip()}")
    return kernel_id


def get_status(token, kernel_id):
    result = _run_with_token(token, ["kernels", "status", kernel_id], timeout=30)
    if result.returncode != 0:
        raise KaggleCliError(f"kernel status check failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def retrieve_output(token, kernel_id, dest_dir, file_pattern=None):
    os.makedirs(dest_dir, exist_ok=True)
    args = ["kernels", "output", kernel_id, "-p", dest_dir]
    if file_pattern:
        args += ["--file-pattern", file_pattern]
    result = _run_with_token(token, args, timeout=120)
    if result.returncode != 0:
        raise KaggleCliError(f"kernel output retrieval failed: {result.stderr.strip() or result.stdout.strip()}")
    return [os.path.join(dest_dir, name) for name in os.listdir(dest_dir)]
