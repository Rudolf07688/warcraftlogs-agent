"""Error envelope wiring (feature 006, contracts/auth-api.md).

Auth/admin endpoints raise ``HTTPException`` with a dict detail ``{"code", "message"}``;
this handler reshapes those into the ``{"error": {code, message, request_id}}`` envelope.
HTTPExceptions with a plain-string detail (the pre-existing endpoints) keep FastAPI's
default ``{"detail": ...}`` shape, so no existing behavior changes.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


async def _envelope_http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        request_id = request.headers.get("x-request-id")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": detail.get("code"),
                    "message": detail.get("message", ""),
                    "request_id": request_id,
                }
            },
            headers=getattr(exc, "headers", None),
        )
    return await http_exception_handler(request, exc)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _envelope_http_exception_handler)
