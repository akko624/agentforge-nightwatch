"""Submit a Skill ZIP to a trusted SQSP HTTP API without executing its contents."""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
DEFAULT_MODES = ["schema", "static", "quality"]


class ApiFailure(RuntimeError):
    """A compact API error which deliberately does not echo arbitrary response text."""


def require_api_url(value: str, allow_remote: bool) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError("API URL must be an http(s) origin without query or fragment")
    if not allow_remote and parsed.hostname.lower() not in LOOPBACK_HOSTS:
        raise ValueError("Refusing to upload a Skill ZIP to a non-loopback host without --allow-remote")
    return value.rstrip("/")


def read_error(error: HTTPError) -> str:
    try:
        payload = json.loads(error.read().decode("utf-8", "replace"))
        code = payload.get("error", {}).get("code")
        if isinstance(code, str) and code:
            return f"API request failed ({error.code}, {code})"
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        pass
    return f"API request failed ({error.code})"


def request_json(url: str, *, method: str = "GET", body: bytes | None = None, content_type: str | None = None) -> dict:
    headers = {"Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - URL is explicitly gated above.
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise ApiFailure(read_error(error)) from None
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiFailure("SQSP API is unavailable or returned an invalid response") from error
    if not isinstance(data, dict):
        raise ApiFailure("SQSP API returned an invalid JSON object")
    return data


def multipart_upload(path: Path, owner_label: str) -> tuple[bytes, str]:
    boundary = f"----sqsp-{uuid.uuid4().hex}"
    filename = path.name.replace('"', "")
    content_type = mimetypes.guess_type(filename)[0] or "application/zip"
    fields = [("owner_label", owner_label.encode("utf-8")), ("file", path.read_bytes())]
    parts: list[bytes] = []
    for name, value in fields:
        parts.append(f"--{boundary}\r\n".encode())
        if name == "file":
            parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
            parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        else:
            parts.append(b'Content-Disposition: form-data; name="owner_label"\r\n\r\n')
        parts.extend((value, b"\r\n"))
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def require_new_output(value: str) -> Path:
    output = Path(value).expanduser().resolve()
    if output.exists() or not output.parent.is_dir():
        raise ValueError("--output must be a new file whose parent directory already exists")
    return output


def scan(api_url: str, archive: Path, output: Path, owner_label: str, timeout_seconds: int) -> dict:
    ready = request_json(f"{api_url}/readyz")
    if ready.get("status") != "ready":
        raise ApiFailure("SQSP API is not ready")
    body, content_type = multipart_upload(archive, owner_label)
    imported = request_json(f"{api_url}/api/v1/skills/upload", method="POST", body=body, content_type=content_type)
    version_id = imported.get("version_id")
    if not isinstance(version_id, str):
        raise ApiFailure("SQSP upload response omitted version_id")
    created = request_json(
        f"{api_url}/api/v1/scans", method="POST",
        body=json.dumps({"version_id": version_id, "modes": DEFAULT_MODES, "force": True}).encode("utf-8"),
        content_type="application/json",
    )
    scan_id = created.get("scan_id")
    if not isinstance(scan_id, str):
        raise ApiFailure("SQSP scan response omitted scan_id")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        summary = request_json(f"{api_url}/api/v1/scans/{scan_id}")
        status = summary.get("status")
        if status in {"PARTIAL", "COMPLETED"}:
            report = request_json(f"{api_url}/api/v1/scans/{scan_id}/report")
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return {"scan_id": scan_id, "status": status, "release_decision": summary.get("release_decision"), "report": str(output)}
        if status == "FAILED":
            code = summary.get("error_code") if isinstance(summary.get("error_code"), str) else "UNKNOWN"
            raise ApiFailure(f"SQSP scan failed ({code})")
        time.sleep(0.5)
    raise ApiFailure("Timed out waiting for the independent SQSP Worker")


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely scan a Skill ZIP through a trusted SQSP API; never executes the archive")
    parser.add_argument("--skill-zip", required=True, type=Path)
    parser.add_argument("--output", required=True, help="New JSON report path; existing files are refused")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--owner-label", default="", help="Optional non-secret local label")
    parser.add_argument("--timeout", type=int, default=90, help="Worker wait limit in seconds (1-600)")
    parser.add_argument("--allow-remote", action="store_true", help="Explicitly permit upload to a non-loopback API")
    args = parser.parse_args()
    try:
        archive = args.skill_zip.expanduser().resolve()
        if not archive.is_file() or archive.suffix.lower() != ".zip":
            raise ValueError("--skill-zip must be an existing .zip file")
        if not 1 <= args.timeout <= 600:
            raise ValueError("--timeout must be between 1 and 600 seconds")
        result = scan(require_api_url(args.api_url, args.allow_remote), archive, require_new_output(args.output), args.owner_label, args.timeout)
    except (ApiFailure, ValueError, OSError) as error:
        print(f"scan_skill: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
