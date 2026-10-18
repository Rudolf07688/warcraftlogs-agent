"""Startup progress tracking + readiness gate.

The lifespan in ``main.py`` runs its boot steps (ADK session tables, guide registry,
model discovery, ...) in a background task so uvicorn can start listening right away.
While those steps run, ``StartupTracker`` records per-step progress that ``/api/health``
exposes, and ``ReadinessGate`` answers every other request with ``503`` so nothing
reads half-initialised ``app.state``. The frontend polls the health endpoint and shows a
boot overlay until ``ready`` flips to true.

When no tracker is installed on ``app.state`` (tests drive the app without a lifespan)
the gate is a no-op, mirroring ``model_state.get_model_state``'s fallback behaviour.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# The ordered boot steps, as shown in the frontend overlay.
BOOT_STEPS: tuple[tuple[str, str], ...] = (
    ("serializers", "Preparing model serializers"),
    ("sessions", "Preparing conversation session tables"),
    ("roster", "Loading the class and spec list"),
    ("guides", "Connecting the coaching briefs"),
    ("models", "Discovering and validating AI models"),
    ("greeting", "Warming up Barnaby's greeting"),
)

# Paths that stay reachable while booting (health probes + the frontend poll).
HEALTH_PATHS: frozenset[str] = frozenset({"/health", "/api/health"})


@dataclass
class StartupStep:
    key: str
    label: str
    status: str = "pending"  # pending | running | done | skipped | failed
    detail: str | None = None
    ms: int | None = None


class StartupTracker:
    """Mutable record of the boot sequence, snapshot-able as JSON."""

    def __init__(self, steps: tuple[tuple[str, str], ...] = BOOT_STEPS) -> None:
        self.steps: list[StartupStep] = [StartupStep(key=k, label=l) for k, l in steps]
        self.phase = "booting"  # booting | ready | failed
        self.error: str | None = None
        self.started_at = time.monotonic()
        self.finished_at: float | None = None
        self._running_since: dict[str, float] = {}

    # --- step transitions -------------------------------------------------------

    def _step(self, key: str) -> StartupStep:
        for s in self.steps:
            if s.key == key:
                return s
        raise KeyError(key)

    def begin(self, key: str) -> None:
        self._step(key).status = "running"
        self._running_since[key] = time.monotonic()

    def _close(self, key: str, status: str, detail: str | None) -> None:
        step = self._step(key)
        step.status = status
        step.detail = detail
        started = self._running_since.pop(key, None)
        if started is not None:
            step.ms = int((time.monotonic() - started) * 1000)

    def done(self, key: str, detail: str | None = None) -> None:
        self._close(key, "done", detail)

    def skip(self, key: str, detail: str | None = None) -> None:
        self._close(key, "skipped", detail)

    def fail(self, key: str, exc: BaseException) -> None:
        msg = f"{type(exc).__name__}: {exc}"
        self._close(key, "failed", msg)
        self.phase = "failed"
        self.error = f"{self._step(key).label} failed — {msg}"
        self.finished_at = time.monotonic()

    def finish(self) -> None:
        if self.phase == "booting":
            self.phase = "ready"
            self.finished_at = time.monotonic()

    async def run(
        self,
        key: str,
        fn: Callable[[], Awaitable[Any]],
        *,
        optional: bool = False,
        detail: Callable[[Any], str | None] | None = None,
    ) -> Any:
        """Run ``fn`` as step ``key``.

        A failure in a required step marks the whole boot as failed and re-raises;
        an ``optional`` step is marked skipped and the exception swallowed (logged).
        """
        self.begin(key)
        try:
            result = await fn()
        except Exception as exc:  # noqa: BLE001
            if optional:
                logger.warning("Startup step %r skipped: %s", key, exc)
                self.skip(key, f"{type(exc).__name__}: {exc}")
                return None
            logger.exception("Startup step %r failed", key)
            self.fail(key, exc)
            raise
        self.done(key, detail(result) if detail else None)
        return result

    # --- read side ----------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self.phase == "ready"

    @property
    def current(self) -> StartupStep | None:
        return next((s for s in self.steps if s.status == "running"), None)

    def snapshot(self) -> dict[str, Any]:
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        cur = self.current
        return {
            "phase": self.phase,
            "ready": self.ready,
            "error": self.error,
            "elapsed_ms": int((end - self.started_at) * 1000),
            "current_step": cur.key if cur else None,
            "steps": [asdict(s) for s in self.steps],
        }


class ReadinessGate:
    """Pure ASGI middleware: 503 for HTTP, 1013 close for WebSocket, until boot completes.

    Health paths always pass. With no tracker on ``app.state`` everything passes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        tracker = _tracker_for(scope)
        if tracker is None or tracker.ready or scope.get("path") in HEALTH_PATHS:
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            # Accept nothing; 1013 = "Try Again Later".
            await receive()
            await send({"type": "websocket.close", "code": 1013})
            return

        failed = tracker.phase == "failed"
        cur = tracker.current
        body = {
            "error": {
                "code": "backend_failed" if failed else "backend_starting",
                "message": tracker.error
                if failed
                else f"Backend is starting up ({cur.label if cur else 'finishing'})…",
            },
            "startup": tracker.snapshot(),
        }
        response = JSONResponse(body, status_code=503, headers={"Retry-After": "2"})
        await response(scope, receive, send)


def _tracker_for(scope: Scope) -> StartupTracker | None:
    app = scope.get("app")
    state = getattr(app, "state", None)
    tracker = getattr(state, "startup", None)
    return tracker if isinstance(tracker, StartupTracker) else None
