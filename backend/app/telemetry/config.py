"""Telemetry configuration from the process environment (feature 054).

Read before FastAPI and ADK are imported, so this module must not import ``backend.app.config``
(that one imports ADK). It loads ``.env`` the way ``config.py`` does, so a local run picks up
the same values the settings will.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENVIRONMENTS = frozenset({"dev", "ci", "prod"})
_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class TelemetryConfig:
    """Whether to export, the deployment environment and the version every signal carries;
    where span profiles go (feature 059), empty when profiling is off."""

    enabled: bool
    environment: str
    version: str
    profiles_address: str = ""

    @property
    def content_allowed(self) -> bool:
        """Prompt, response and tool content may leave the process in ``dev`` only (fail-safe)."""
        return self.environment == "dev"


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


def load_config() -> TelemetryConfig:
    """On iff ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set; ``WCL_ENVIRONMENT`` outside dev/ci/prod
    (unset included) is ``unknown``, which is a lockdown like ci and prod. Span profiles need
    telemetry on and ``PYROSCOPE_SERVER_ADDRESS`` set."""
    # Same switch as config.LOAD_DOTENV (the test suite sets WCL_LOAD_DOTENV=0).
    if os.getenv("WCL_LOAD_DOTENV", "1").strip().lower() not in ("0", "false", "no"):
        load_dotenv()
    enabled = bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip())
    environment = os.getenv("WCL_ENVIRONMENT", "").strip().lower()
    if environment not in ENVIRONMENTS:
        environment = "unknown"
    version = os.getenv("WCL_GIT_SHA", "").strip()
    if enabled and not version:
        version = _git_sha()
    profiles_address = os.getenv("PYROSCOPE_SERVER_ADDRESS", "").strip() if enabled else ""
    return TelemetryConfig(
        enabled=enabled, environment=environment, version=version or "unknown", profiles_address=profiles_address
    )
