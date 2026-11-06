import hashlib
import io
import stat
import struct
import zipfile

import pytest

from backend.app.core.config import Settings
from backend.app.core.errors import PlatformError
from backend.app.ingest.safe_zip import read_archive
from backend.app.ingest.store import LocalArtifactStore

SKILL = b"---\nname: safe-helper\ndescription: Summarize a supplied CSV file when asked.\n---\n# Helper\n"


def make_zip(entries=None, compression=zipfile.ZIP_DEFLATED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        for name, content in entries or [("safe-helper/SKILL.md", SKILL)]:
            archive.writestr(name, content)
    return stream.getvalue()


def test_import_root_and_flat_layout_and_inventory():
    data = make_zip([("safe-helper/SKILL.md", SKILL), ("safe-helper/.hidden", b"hidden evidence"),
                     ("safe-helper/scripts/job.py", b"raise RuntimeError('NEVER EXECUTE')"),
                     ("safe-helper/image.bin", b"\x00\x01")])
    result = read_archive(data, Settings())
    assert result.root_name == "safe-helper"
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    assert result.files["SKILL.md"] == SKILL
    assert {item["path"] for item in result.inventory} == set(result.files)
    hidden = next(item for item in result.inventory if item["path"] == ".hidden")
    assert hidden["hidden"] is True
    assert hidden["sha256"] == hashlib.sha256(b"hidden evidence").hexdigest()
    assert next(item for item in result.inventory if item["path"] == "image.bin")["parseable"] is False
    assert read_archive(make_zip([("SKILL.md", SKILL)]), Settings()).root_name is None


@pytest.mark.parametrize("path", [
    "../../outside.txt", "/tmp/outside", "C:/Windows/escape", "\\\\server\\share\\escape",
    "root/../escape", "root\\escape", "root//escape", "root/./escape", "root/file:stream",
    "root/CON", "root/nul.txt", "root/COM1.log", "root/LPT9", "root/CONIN$", "root/CONOUT$", "root/file.", "root/file ",
    "root/\u202eescape", "root/\uff0e\uff0e/escape", "root/\u2215escape", "root/e\u0301.txt",
    "root/\u2024\u2024/escape", "root/a?b", "root/a\x01b",
])
def test_reject_unsafe_paths_without_writes(path, tmp_path):
    outside = tmp_path / "outside.txt"
    # ZipFile's writer canonicalizes backslashes on Windows. Reintroduce the
    # adversarial bytes into both headers rather than accidentally testing its
    # sanitized output.
    archive_data = make_zip([("SKILL.md", SKILL), (path, b"forbidden")])
    if path == "root\\escape":
        archive_data = archive_data.replace(b"root/escape", b"root\\escape")
    with pytest.raises(PlatformError) as exc:
        read_archive(archive_data, Settings())
    assert exc.value.code == "INVALID_ARCHIVE"
    assert not outside.exists()


@pytest.mark.parametrize("mode", [stat.S_IFLNK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK])
def test_reject_symlink_and_unix_special_files(mode):
    special = zipfile.ZipInfo("safe-helper/link")
    special.create_system = 3
    special.external_attr = (mode | 0o777) << 16
    with pytest.raises(PlatformError) as exc:
        read_archive(make_zip([("safe-helper/SKILL.md", SKILL), (special, b"../../outside")]), Settings())
    assert exc.value.code == "INVALID_ARCHIVE"


def test_reject_ambiguous_duplicates_and_ancestor_collisions():
    for entries in [
        [("SKILL.md", SKILL), ("A.txt", b"a"), ("a.txt", b"b")],
        [("SKILL.md", SKILL), ("a", b"a"), ("a/file.txt", b"b")],
        [("SKILL.md", SKILL), ("a", b"a"), ("a/", b"")],
    ]:
        with pytest.raises(PlatformError) as exc:
            read_archive(make_zip(entries), Settings())
        assert exc.value.code == "INVALID_ARCHIVE"
    with pytest.warns(UserWarning):
        duplicate = make_zip([("SKILL.md", SKILL), ("SKILL.md", SKILL)])
    with pytest.raises(PlatformError):
        read_archive(duplicate, Settings())


@pytest.mark.parametrize("entries", [
    [("readme.md", b"missing")], [("one/SKILL.md", SKILL), ("two/SKILL.md", SKILL)],
    [("one/SKILL.md", SKILL), ("outside.txt", b"outside")],
    [("one/SKILL.md", SKILL), ("other/", b"")],
])
def test_reject_invalid_skill_root(entries):
    with pytest.raises(PlatformError) as exc:
        read_archive(make_zip(entries), Settings())
    assert exc.value.code == "INVALID_ARCHIVE"


@pytest.mark.parametrize(("entries", "limits", "reason"), [
    ([("SKILL.md", SKILL)], {"max_upload_bytes": 20}, "upload_size"),
    ([("SKILL.md", SKILL), ("a.txt", b"a")], {"max_entries": 1}, "entry_count"),
    ([("SKILL.md", SKILL), ("a/b/c.txt", b"a")], {"max_depth": 2}, "path_depth"),
    ([("SKILL.md", SKILL), ("big.txt", b"a" * 200)], {"max_file_bytes": 100}, "file_size"),
    ([("SKILL.md", SKILL), ("a.txt", b"a" * 80), ("b.txt", b"b" * 80)],
     {"max_file_bytes": 100, "max_expanded_bytes": 160}, "expanded_size"),
    ([("SKILL.md", SKILL), ("bomb.txt", b"a" * 10000)], {}, "compression_ratio"),
])
def test_archive_resource_limits(entries, limits, reason):
    with pytest.raises(PlatformError) as exc:
        read_archive(make_zip(entries), Settings(**limits))
    assert exc.value.code == "ARCHIVE_LIMIT"
    assert exc.value.status == 413
    assert exc.value.details["reason"] == reason


def test_empty_file_allowed_unknown_or_corrupt_archive_rejected():
    result = read_archive(make_zip([("SKILL.md", SKILL), ("empty.txt", b"")]), Settings())
    assert result.files["empty.txt"] == b""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w"):
        pass
    for invalid in [b"", b"not zip", stream.getvalue(), make_zip()[:-15]]:
        with pytest.raises(PlatformError) as exc:
            read_archive(invalid, Settings())
        assert exc.value.code == "INVALID_ARCHIVE"


def test_crc_corruption_rejected():
    data = make_zip(compression=zipfile.ZIP_STORED)
    bad = data.replace(SKILL, b"X" + SKILL[1:])
    with pytest.raises(PlatformError) as exc:
        read_archive(bad, Settings())
    assert exc.value.code == "INVALID_ARCHIVE"


def test_null_name_encryption_and_unsupported_compression_rejected():
    null_name = make_zip([("SKILL.md", SKILL), ("badXname", b"bad")]).replace(b"badXname", b"bad\x00name")
    data = bytearray(make_zip())
    central = data.index(b"PK\x01\x02")
    struct.pack_into("<H", data, central + 8, 1)
    for invalid in [null_name, bytes(data), make_zip(compression=zipfile.ZIP_BZIP2)]:
        with pytest.raises(PlatformError) as exc:
            read_archive(invalid, Settings())
        assert exc.value.code == "INVALID_ARCHIVE"


def test_unix_hardlink_metadata_and_windows_reparse_point_rejected():
    hardlink = zipfile.ZipInfo("link")
    hardlink.extra = struct.pack("<HH", 0x756E, 3) + b"abc"
    reparse = zipfile.ZipInfo("junction")
    reparse.external_attr = 0x400
    for info in [hardlink, reparse]:
        with pytest.raises(PlatformError):
            read_archive(make_zip([("SKILL.md", SKILL), (info, b"anything")]), Settings())


def test_local_store_immutable_content_addressing(tmp_path):
    store = LocalArtifactStore(tmp_path / "objects")
    key = "artifacts/ab/" + hashlib.sha256(b"archive").hexdigest() + ".zip"
    assert store.put(b"archive", key) == key
    assert store.read(key) == b"archive"
    assert store.put(b"archive", key) == key
    with pytest.raises(PlatformError) as exc:
        store.put(b"different", key)
    assert exc.value.code == "ARTIFACT_CONFLICT"
    assert not list((tmp_path / "objects").rglob(".upload-*"))


@pytest.mark.parametrize("key", ["../escape", "/tmp/escape", "C:/escape", "a\\b", "a//b", "a/./b", "a/../b", ""])
def test_local_store_rejects_unsafe_keys(tmp_path, key):
    store = LocalArtifactStore(tmp_path / "objects")
    with pytest.raises(PlatformError):
        store.put(b"data", key)
    with pytest.raises(PlatformError):
        store.read(key)


def test_local_store_missing_object(tmp_path):
    with pytest.raises(PlatformError) as exc:
        LocalArtifactStore(tmp_path).read("missing.zip")
    assert exc.value.code == "ARTIFACT_NOT_FOUND"


def test_local_store_concurrent_identical_writes_are_idempotent(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    store = LocalArtifactStore(tmp_path / "objects")
    data = b"complete object" * 1000
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.put(data, "shared/object.zip"), range(16)))
    assert results == ["shared/object.zip"] * 16
    assert store.read("shared/object.zip") == data
    assert not list((tmp_path / "objects").rglob(".upload-*"))


def test_central_directory_quota_checked_before_zipinfo_allocation(monkeypatch):
    honest = make_zip([("SKILL.md", SKILL), ("a", b""), ("b", b"")])
    forged = bytearray(honest)
    eocd = forged.rfind(b"PK\x05\x06")
    # Lie about both entry counts. The directory walk must still enforce quota.
    struct.pack_into("<HH", forged, eocd + 8, 1, 1)

    def must_not_construct(*args, **kwargs):
        pytest.fail("ZipFile allocated ZipInfo objects before entry quota check")

    monkeypatch.setattr(zipfile, "ZipFile", must_not_construct)
    for data in [honest, bytes(forged)]:
        with pytest.raises(PlatformError) as exc:
            read_archive(data, Settings(max_entries=2))
        assert exc.value.code == "ARCHIVE_LIMIT"
        assert exc.value.details["reason"] == "entry_count"


@pytest.mark.parametrize("kind", ["count", "zip64", "offset", "disk", "trailing", "record_length"])
def test_reject_malformed_central_directory_before_zipfile(monkeypatch, kind):
    data = bytearray(make_zip())
    eocd = data.rfind(b"PK\x05\x06")
    central = data.index(b"PK\x01\x02")
    if kind == "count":
        struct.pack_into("<HH", data, eocd + 8, 2, 2)
    elif kind == "zip64":
        struct.pack_into("<HH", data, eocd + 8, 0xFFFF, 0xFFFF)
    elif kind == "offset":
        struct.pack_into("<I", data, eocd + 16, 0x12345678)
    elif kind == "disk":
        struct.pack_into("<H", data, eocd + 4, 1)
    elif kind == "trailing":
        data.extend(b"unindexed payload")
    elif kind == "record_length":
        struct.pack_into("<H", data, central + 28, 0xFFFF)

    def must_not_construct(*args, **kwargs):
        pytest.fail("Malformed central directory reached ZipFile")

    monkeypatch.setattr(zipfile, "ZipFile", must_not_construct)
    with pytest.raises(PlatformError) as exc:
        read_archive(bytes(data), Settings())
    assert exc.value.code == "INVALID_ARCHIVE"


def test_local_zip64_header_is_explicitly_unsupported():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        with archive.open("SKILL.md", "w", force_zip64=True) as member:
            member.write(SKILL)
    with pytest.raises(PlatformError) as exc:
        read_archive(stream.getvalue(), Settings())
    assert exc.value.code == "INVALID_ARCHIVE"


def test_examples_package_deterministically_and_parse_without_execution(tmp_path):
    from backend.app.skill.parser import parse_skill
    from scripts.seed_examples import ROOT, package_directory

    for name in ("benign-skill", "suspicious-skill"):
        directory = ROOT / "examples" / name
        first = package_directory(directory)
        assert first == package_directory(directory)
        archive = read_archive(first, Settings())
        parsed = parse_skill(archive.files, archive.root_name)
        assert parsed.name == name
        assert not parsed.issues
    first = read_archive(package_directory(ROOT / "examples/suspicious-skill"), Settings())
    second = read_archive(package_directory(ROOT / "examples/suspicious-skill", repaired=True), Settings())
    assert first.sha256 != second.sha256
    assert first.root_name == second.root_name == "suspicious-skill"
    assert b"return eval(user_input)" in first.files["scripts/payload.py"]
    assert b"return eval(user_input)" not in second.files["scripts/payload.py"]
    assert parse_skill(second.files, second.root_name).frontmatter["metadata"]["version"] == "1.0.1"
