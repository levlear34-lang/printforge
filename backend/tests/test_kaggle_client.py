"""Tests for the subprocess-invocation details of kaggle_client -- these
subprocess.run mocks stay local to this file rather than being covered
transitively through generation.py's tests, since a real production bug
(hardcoded "python" instead of sys.executable, causing a raw 500 on
Render where only python3 is on PATH) slipped through until it was hit
live. See CLAUDE.md's Progress Log for the incident.
"""
import subprocess
import sys
from unittest.mock import patch

import pytest

from app.services import kaggle_client


def test_run_with_token_invokes_sys_executable():
    with patch.object(subprocess, "run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        kaggle_client._run_with_token("fake-token", ["config", "view"])
    called_args = mock_run.call_args[0][0]
    assert called_args[0] == sys.executable
    assert called_args[1:3] == ["-m", "kaggle"]


def test_run_with_token_never_leaves_kaggle_config_dir_set():
    with patch.object(subprocess, "run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch.dict("os.environ", {"KAGGLE_CONFIG_DIR": "/should/be/removed"}):
            kaggle_client._run_with_token("fake-token", ["config", "view"])
    passed_env = mock_run.call_args.kwargs["env"]
    assert "KAGGLE_CONFIG_DIR" not in passed_env
    assert passed_env["KAGGLE_API_TOKEN"] == "fake-token"


def test_run_with_token_wraps_subprocess_launch_failure():
    """Regression guard for the real Render incident: a subprocess that
    fails to even launch (missing interpreter, etc.) must surface as a
    clean KaggleCliError, not a bare unhandled exception.
    """
    with patch.object(subprocess, "run", side_effect=FileNotFoundError("no such file: python")):
        with pytest.raises(kaggle_client.KaggleCliError):
            kaggle_client._run_with_token("fake-token", ["config", "view"])


def test_run_with_token_wraps_timeout():
    with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="kaggle", timeout=30)):
        with pytest.raises(kaggle_client.KaggleCliError):
            kaggle_client._run_with_token("fake-token", ["config", "view"], timeout=30)
