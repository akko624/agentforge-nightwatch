def test_upload_content_length_rejected_before_multipart_parse(client, configured):
    configured.max_upload_bytes = 1024
    response = client.post("/api/v1/skills/upload", content=b"", headers={"content-length": "70000", "content-type": "application/zip"})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "ARCHIVE_LIMIT"


def test_chunked_upload_is_bounded_before_multipart_parse(client, configured):
    configured.max_upload_bytes = 1024
    def chunks():
        yield b"x" * 40000
        yield b"x" * 40000
    response = client.post("/api/v1/skills/upload", content=chunks(), headers={"content-type": "application/octet-stream"})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "ARCHIVE_LIMIT"


def test_error_response_does_not_echo_request_secret(client):
    secret = "sk-ExampleSyntheticSecretOnly0123456789"
    response = client.post("/api/v1/scans", json={"version_id": "missing", "unknown": secret})
    assert response.status_code == 422
    assert secret not in response.text
    response = client.post("/api/v1/scans", json={"version_id": "missing", secret: "value"})
    assert secret not in response.text
