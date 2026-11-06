"""Exercise the running API and its independent Worker using only stdlib HTTP.

This script never imports the application, invokes run_scan or executes a Skill.
It creates real scan records in the selected development server.
"""

import argparse
import io
import json
import time
import uuid
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"COMPLETED", "PARTIAL", "FAILED"}


def request_json(base: str, path: str, *, method: str = "GET", data: bytes | None = None,
                 content_type: str | None = None, expected: int | None = None) -> dict:
    headers = {"Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    request = Request(base.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=15) as response:
            status, body = response.status, response.read()
    except HTTPError as error:
        status, body = error.code, error.read()
    if expected is not None and status != expected:
        raise AssertionError(f"{method} {path}: expected HTTP {expected}, received {status}")
    result = json.loads(body)
    if status >= 400 and expected is None:
        code = result.get("error", {}).get("code", "UNKNOWN")
        raise AssertionError(f"{method} {path}: HTTP {status}, error {code}")
    return result


def upload(base: str, content: bytes, filename: str, *, expected: int = 201) -> dict:
    boundary = f"sqsp-smoke-{uuid.uuid4().hex}"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            "Content-Type: application/zip\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return request_json(base, "/api/v1/skills/upload", method="POST", data=body,
                        content_type=f"multipart/form-data; boundary={boundary}", expected=expected)


def scan(base: str, version_id: str, timeout: float) -> tuple[str, dict]:
    request = {"version_id": version_id, "modes": ["schema", "static", "quality", "dynamic"], "force": True}
    created = request_json(base, "/api/v1/scans", method="POST", data=json.dumps(request).encode(),
                           content_type="application/json", expected=202)
    scan_id = created["scan_id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        summary = request_json(base, f"/api/v1/scans/{scan_id}")
        if summary["status"] in TERMINAL:
            if summary["status"] == "FAILED":
                raise AssertionError(f"Scan {scan_id} failed: {summary.get('error_code')}")
            assert summary["quality_score"] is None, "A complete quality score must not be fabricated"
            assert summary["stages"]["dynamic"]["status"] == "UNAVAILABLE", "Default sandbox must fail closed"
            report = request_json(base, f"/api/v1/scans/{scan_id}/report")
            assert report["quality"]["score"] is None
            assert report["quality"]["coverage"] <= 0.4
            assert report["provenance"]["ruleset_sha256"]
            assert report["provenance"]["policy_version"]
            return scan_id, report
        time.sleep(0.2)
    raise TimeoutError(f"Scan {scan_id} did not complete in {timeout:g}s; start the independent Worker")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SQSP real HTTP import/worker/report/compare smoke checks")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    request_json(args.base_url, "/readyz", expected=200)
    reports = {}
    for name in ("benign-skill", "suspicious-skill", "suspicious-skill-v2"):
        fixture = ROOT / "examples" / "zips" / f"{name}.zip"
        if not fixture.is_file():
            raise SystemExit("Example ZIP missing; run python scripts/seed_examples.py first")
        imported = upload(args.base_url, fixture.read_bytes(), fixture.name)
        reports[name] = scan(args.base_url, imported["version_id"], args.timeout)
        print(f"{name}: real Worker report received ({reports[name][0]})")
    benign = reports["benign-skill"][1]
    suspicious = reports["suspicious-skill"][1]
    assert not benign["security"]["findings"], "Benign fixture should not have security findings"
    assert len({item["category"] for item in suspicious["security"]["findings"]}) >= 4
    assert suspicious["decision"]["status"] == "BLOCK"
    parameters = urlencode({"left": reports["suspicious-skill"][0], "right": reports["suspicious-skill-v2"][0]})
    difference = request_json(args.base_url, f"/api/v1/compare?{parameters}")
    assert any(item["rule_id"] == "SQSP-S003" for item in difference["resolved_findings"]), "The v2 repair must resolve S003"
    malicious = io.BytesIO()
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("../../outside.txt", "inert traversal test")
    rejection = upload(args.base_url, malicious.getvalue(), "traversal.zip", expected=400)
    assert rejection["error"]["code"] == "INVALID_ARCHIVE"
    assert rejection["error"]["request_id"]
    print("PASS: import -> independent Worker -> report -> version comparison; traversal rejected; score null; sandbox UNAVAILABLE")


if __name__ == "__main__":
    main()
