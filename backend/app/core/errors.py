from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from backend.app.core.redaction import redact_object


class PlatformError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: dict | None = None):
        self.code, self.message, self.status, self.details = code, message, status, details or {}


def install_error_handlers(app: FastAPI) -> None:
    def response(request: Request, code: str, message: str, status: int, details: dict | None = None):
        return JSONResponse(status_code=status, content={"error": {
            "code": code, "message": message, "details": details or {},
            "request_id": getattr(request.state, "request_id", str(uuid4())),
        }})

    @app.exception_handler(PlatformError)
    async def platform_error(request: Request, exc: PlatformError):
        return response(request, exc.code, exc.message, exc.status, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Pydantic's input/ctx may contain untrusted source or credentials.
        issues = redact_object([{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()])
        return response(request, "VALIDATION_ERROR", "Invalid request", 422, {"issues": issues})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return response(request, "HTTP_ERROR", "Request could not be completed", exc.status_code)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        return response(request, "INTERNAL_ERROR", "Internal service error", 500)
