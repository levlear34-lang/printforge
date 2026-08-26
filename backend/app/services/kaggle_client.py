"""Thin wrapper around the `kaggle` CLI, scoped to a single visitor-supplied
token per call.

Unlike AI_3D_FACTORY's kaggle_generator.py (which reads one fixed credential
from ~/.kaggle for the developer's own account), every call here takes the
token as an explicit argument and passes it via the KAGGLE_API_TOKEN
environment variable for that one subprocess call only -- never written to
any file, never logged, gone the moment the call returns. The in-memory job
record (see jobs.py) is the only place a token is held between calls, for
the lifetime of that job.

IMPORTANT, found the hard way (see CLAUDE.md Milestone 3 Progress Log): this
version of the `kaggle` CLI (2.2.4, using `kagglesdk`) does NOT read
KAGGLE_CONFIG_DIR for access-token auth at all -- its lookup order is
KAGGLE_API_TOKEN env var, then unconditionally ~/.kaggle/access_token on
this machine, full stop. A first attempt used a per-request temp
KAGGLE_CONFIG_DIR (the documented mechanism for the older kaggle.json
auth), which silently did nothing: every call actually authenticated as
this developer's own real Kaggle account regardless of what token was
supplied, including garbage tokens. Confirmed via a real test (a
random-bytes fake token still resolved to the developer's real username)
before trusting the fix below, which uses the environment variable this
CLI version actually checks.
"""
import json
import os
import subprocess
import sys


class KaggleAuthError(Exception):
    """The provided token was rejected by Kaggle (invalid/expired/malformed)."""


class KaggleCliError(Exception):
    """A kaggle CLI call failed for a reason other than auth."""


def _run_with_token(token, args, timeout=120):
    env = dict(os.environ)
    env.pop("KAGGLE_CONFIG_DIR", None)
    env["KAGGLE_API_TOKEN"] = token.strip()
    env["PYTHONUTF8"] = "1"

    try:
        return subprocess.run(
            # sys.executable, not the literal string "python" -- found via
            # a real 500 on Render's live deploy (bare, unhandled
            # FileNotFoundError, not one of this module's own exception
            # types): Render's container only has `python3` on PATH, not
            # `python`, so the hardcoded command silently didn't exist
            # there. sys.executable is the absolute path to the exact
            # interpreter already running this process, correct
            # regardless of what aliases a given deployment environment
            # does or doesn't set up.
            [sys.executable, "-m", "kaggle"] + args,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        # Belt-and-suspenders alongside the sys.executable fix above: any
        # future failure to even launch the subprocess (missing
        # interpreter, timeout, etc.) surfaces as a clean KaggleCliError
        # instead of a bare unhandled exception -- exactly the class of
        # bug that caused the raw 500 this comment is explaining.
        raise KaggleCliError(f"Failed to run the kaggle CLI: {exc}") from exc


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
