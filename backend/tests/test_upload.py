from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


def archive_files(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def valid_zip(name="test-skill", body="# Test\n1. Read input\n2. Write output\n", extra="") -> bytes:
    return archive_files({f"{name}/SKILL.md": f"---\nname: {name}\ndescription: Use when summarizing local input files.\nmetadata:\n  version: '1.0'\n{extra}---\n{body}".encode()})


def upload(client, data: bytes):
    return client.post("/api/v1/skills/upload", files={"file": ("test.zip", data, "application/zip")})


def test_upload_deduplicates_and_lists_versions(client):
    first = upload(client, valid_zip())
    assert first.status_code == 201, first.text
    second = upload(client, valid_zip())
    assert first.json() == second.json()
    skills = client.get("/api/v1/skills").json()
    assert skills["total"] == 1
    versions = client.get(f"/api/v1/skills/{first.json()['skill_id']}/versions").json()["items"]
    assert len(versions) == 1
    assert versions[0]["file_inventory"][0]["sha256"]


def test_upload_rejects_bad_zip_and_reports_safe_error(client):
    response = upload(client, archive_files({"../escape": b"bad"}))
    assert response.status_code in (400, 413)
    assert response.json()["error"]["code"] == "INVALID_ARCHIVE"
    assert client.get("/api/v1/skills").json()["total"] == 0
    response = upload(client, archive_files({"SKILL.md": b"no frontmatter"}))
    assert response.json()["error"]["code"] == "INVALID_FRONTMATTER"
