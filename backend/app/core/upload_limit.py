import json
from uuid import uuid4

from backend.app.core.config import get_settings


class UploadLimitMiddleware:
    """Bound the raw multipart body before the multipart parser can spool files."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or scope.get("path") != "/api/v1/skills/upload":
            await self.app(scope, receive, send)
            return
        limit = get_settings().max_upload_bytes + 65536

        async def rejected():
            body = json.dumps({"error": {"code": "ARCHIVE_LIMIT", "message": "Upload exceeds size limit",
                                          "details": {}, "request_id": str(uuid4())}}).encode()
            await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"x-content-type-options", b"nosniff")]})
            await send({"type": "http.response.body", "body": body})

        for key, value in scope.get("headers", []):
            if key.lower() == b"content-length":
                try:
                    if int(value) > limit:
                        await rejected()
                        return
                except ValueError:
                    await rejected()
                    return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                await rejected()
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
