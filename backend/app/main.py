import json
import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from sqlalchemy import text

from backend.app.core.config import get_settings
from backend.app.core.errors import PlatformError, install_error_handlers
from backend.app.core.upload_limit import UploadLimitMiddleware
from backend.app.db.session import get_engine

logger = logging.getLogger("sqsp.access")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def create_app() -> FastAPI:
    get_settings()  # Fail at startup on invalid configuration.
    app = FastAPI(title="SQSP API", version="0.1.0", openapi_url="/api/v1/openapi.json")
    install_error_handlers(app)
    app.add_middleware(UploadLimitMiddleware)
    from backend.app.api.routes import router
    app.include_router(router)

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        request.state.request_id = str(uuid4())
        start = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Do not log body, headers, query or user-controlled URL path.
        logger.info(json.dumps({"event": "request", "request_id": request.state.request_id,
                                "method": request.method, "status": response.status_code,
                                "duration_ms": round((time.monotonic() - start) * 1000)}))
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/readyz")
    def ready():
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
                connection.execute(text("SELECT id FROM scans LIMIT 1"))
            if get_settings().queue_backend == "redis":
                from redis import Redis
                Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2).ping()
        except Exception:
            raise PlatformError("NOT_READY", "Database migrations or queue unavailable", 503) from None
        return {"status": "ready", "queue": get_settings().queue_backend}

    return app


app = create_app()
