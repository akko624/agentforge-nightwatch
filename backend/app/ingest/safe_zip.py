"""Bounded ZIP decoding. No archive-controlled path is written to disk."""

import hashlib
import io
import re
import stat
import struct
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from backend.app.core.config import Settings
from backend.app.core.errors import PlatformError

_WINDOWS_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9]|LPT[1-9])(?:\..*)?$", re.I)
_CONFUSABLE_SEPARATORS = set("\u2215\u2044\u29f8\uff0f\uff3c\ufe68\u2216\u29f5\u2024\u2025\u2026")
_BINARY_SUFFIXES = {".exe", ".dll", ".so", ".dylib", ".bin", ".com", ".msi", ".wasm"}
_ARCHIVE_SUFFIXES = {".zip", ".gz", ".bz2", ".xz", ".tar", ".7z", ".rar", ".whl", ".jar"}


@dataclass(frozen=True)
class ImportedArchive:
    files: dict[str, bytes]
    inventory: list[dict]
    root_name: str | None
    sha256: str


def _invalid(reason: str) -> None:
    raise PlatformError("INVALID_ARCHIVE", "Unsafe or invalid ZIP archive", 400, {"reason": reason})


def _limit(reason: str) -> None:
    raise PlatformError("ARCHIVE_LIMIT", "Archive exceeds configured resource limits", 413, {"reason": reason})


def _preflight_directory(data: bytes, settings: Settings) -> None:
    """Check quotas before ZipFile allocates a ZipInfo per directory record.

    EOCD entry counts are attacker-controlled and cannot be trusted alone. Walk
    the directory with fixed-size struct reads, stopping at the configured cap.
    ZIP64 / multi-disk / appended data are deliberately unsupported in this MVP.
    """
    end = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if end < 0 or end + 22 > len(data):
        _invalid("missing_end_record")
    disk, directory_disk, disk_count, total_count, size, offset, comment_length = struct.unpack_from(
        "<HHHHIIH", data, end + 4,
    )
    if end + 22 + comment_length != len(data):
        _invalid("trailing_or_truncated_data")
    if disk or directory_disk or disk_count != total_count:
        _invalid("unsupported_multidisk_archive")
    if total_count == 0xFFFF or size == 0xFFFFFFFF or offset == 0xFFFFFFFF or data[max(0, end - 20):end - 16] == b"PK\x06\x07":
        _invalid("unsupported_zip64_archive")
    if total_count > settings.max_entries:
        _limit("entry_count")
    if not total_count or offset + size != end:
        _invalid("invalid_directory_bounds")
    cursor, count, first_local_offset = offset, 0, None
    while cursor < end:
        if cursor + 46 > end or data[cursor:cursor + 4] != b"PK\x01\x02":
            _invalid("invalid_directory_record")
        count += 1
        if count > settings.max_entries:
            _limit("entry_count")
        name_length, extra_length, entry_comment_length = struct.unpack_from("<HHH", data, cursor + 28)
        record_disk = struct.unpack_from("<H", data, cursor + 34)[0]
        local_offset = struct.unpack_from("<I", data, cursor + 42)[0]
        if record_disk or local_offset == 0xFFFFFFFF:
            _invalid("unsupported_multidisk_or_zip64_entry")
        if local_offset >= offset or data[local_offset:local_offset + 4] != b"PK\x03\x04":
            _invalid("invalid_local_header_offset")
        first_local_offset = local_offset if first_local_offset is None else min(first_local_offset, local_offset)
        cursor += 46 + name_length + extra_length + entry_comment_length
        if cursor > end:
            _invalid("invalid_directory_record_length")
    if cursor != end or count != total_count or first_local_offset != 0:
        _invalid("directory_count_or_layout_mismatch")


def _safe_name(info: zipfile.ZipInfo, settings: Settings) -> tuple[str, bool]:
    original = info.orig_filename
    if not original or original != info.filename:
        _invalid("null_or_empty_name")
    if "\\" in original or original.startswith("/") or ":" in original:
        _invalid("absolute_or_ambiguous_path")
    if unicodedata.normalize("NFC", original) != original or unicodedata.normalize("NFKC", original) != original:
        _invalid("noncanonical_unicode_path")
    if any(unicodedata.category(char).startswith("C") or char in _CONFUSABLE_SEPARATORS for char in original):
        _invalid("unicode_or_control_path")
    is_directory = original.endswith("/")
    name = original[:-1] if is_directory else original
    parts = name.split("/")
    if not name or any(part in {"", ".", ".."} for part in parts):
        _invalid("path_traversal")
    if len(parts) > settings.max_depth:
        _limit("path_depth")
    if len(name.encode("utf-8")) > 512:
        _limit("path_length")
    for part in parts:
        if len(part.encode("utf-8")) > 255:
            _limit("path_component_length")
        if part.endswith((".", " ")) or any(char in '<>"|?*' for char in part):
            _invalid("windows_unsafe_path")
        if _WINDOWS_RESERVED.fullmatch(part):
            _invalid("device_path")
    # ZIP Unix type bits may encode symlinks, devices, sockets or FIFOs.
    unix_type = stat.S_IFMT(info.external_attr >> 16)
    expected = stat.S_IFDIR if is_directory else stat.S_IFREG
    if unix_type not in {0, expected} or info.external_attr & 0x400:
        _invalid("link_or_special_file")
    if bool(info.external_attr & 0x10) and not is_directory:
        _invalid("directory_type_mismatch")
    if info.flag_bits & 1:
        _invalid("encrypted_entry")
    if info.extract_version >= 45:
        _invalid("unsupported_zip_version")
    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        _invalid("unsupported_compression")
    # ASi Unix / old PKWARE Unix metadata can contain link targets. Do not
    # interpret their vendor-specific link semantics in this implementation.
    offset = 0
    while offset < len(info.extra):
        if offset + 4 > len(info.extra):
            _invalid("malformed_extra_field")
        field_id, field_length = struct.unpack_from("<HH", info.extra, offset)
        offset += 4
        if offset + field_length > len(info.extra):
            _invalid("malformed_extra_field")
        if field_id == 0x0001:
            _invalid("unsupported_zip64_entry")
        if field_id in {0x000D, 0x756E}:
            _invalid("unsupported_unix_link_metadata")
        offset += field_length
    return name, is_directory


def _kind(name: str, content: bytes) -> tuple[str, bool]:
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in _ARCHIVE_SUFFIXES or content.startswith((b"PK\x03\x04", b"\x1f\x8b", b"7z\xbc\xaf\x27\x1c")):
        return "archive", False
    if suffix in _BINARY_SUFFIXES or content.startswith((b"MZ", b"\x7fELF", b"\x00asm")) or b"\x00" in content:
        return "binary", False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return "binary", False
    return "text", True


def read_archive(data: bytes, settings: Settings) -> ImportedArchive:
    if len(data) > settings.max_upload_bytes:
        _limit("upload_size")
    if not data or not data.startswith(b"PK\x03\x04"):
        _invalid("invalid_zip_signature")
    try:
        _preflight_directory(data, settings)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if not entries:
                _invalid("empty_archive")
            if len(entries) > settings.max_entries:
                _limit("entry_count")
            names: dict[str, bool] = {}
            prepared: list[tuple[zipfile.ZipInfo, str, bool]] = []
            announced_total = 0
            for info in entries:
                name, directory = _safe_name(info, settings)
                canonical = name.casefold()
                if canonical in names:
                    _invalid("duplicate_path")
                names[canonical] = directory
                prepared.append((info, name, directory))
                if directory and info.file_size != 0:
                    _invalid("nonempty_directory")
                if info.file_size < 0 or info.compress_size < 0:
                    _invalid("unknown_entry_size")
                if info.file_size > settings.max_file_bytes:
                    _limit("file_size")
                announced_total += info.file_size
                if announced_total > settings.max_expanded_bytes:
                    _limit("expanded_size")
                if info.file_size and (not info.compress_size or info.file_size > info.compress_size * settings.max_compression_ratio):
                    _limit("compression_ratio")
            for name in names:
                for parent in PurePosixPath(name).parents:
                    if str(parent) != "." and names.get(str(parent)) is False:
                        _invalid("file_directory_collision")
            file_names = [name for _, name, directory in prepared if not directory]
            if "SKILL.md" in file_names:
                prefix, root_name = "", None
            else:
                roots = {name.split("/", 1)[0] for name in file_names}
                if len(roots) != 1:
                    _invalid("expected_single_skill_root")
                root_name = next(iter(roots))
                prefix = root_name + "/"
                if prefix + "SKILL.md" not in file_names:
                    _invalid("missing_root_skill_md")
                if any(not name.startswith(prefix) and name != root_name for _, name, _ in prepared):
                    _invalid("entry_outside_skill_root")
            files: dict[str, bytes] = {}
            inventory: list[dict] = []
            actual_total = 0
            for info, name, directory in prepared:
                if directory:
                    continue
                relative = name[len(prefix):]
                chunks: list[bytes] = []
                actual_file = 0
                digest = hashlib.sha256()
                with archive.open(info, "r") as source:
                    while chunk := source.read(min(65536, settings.max_file_bytes - actual_file + 1)):
                        actual_file += len(chunk)
                        actual_total += len(chunk)
                        if actual_file > settings.max_file_bytes:
                            _limit("actual_file_size")
                        if actual_total > settings.max_expanded_bytes:
                            _limit("actual_expanded_size")
                        if actual_file > max(1, info.compress_size) * settings.max_compression_ratio:
                            _limit("actual_compression_ratio")
                        chunks.append(chunk)
                        digest.update(chunk)
                if actual_file != info.file_size:
                    _invalid("entry_size_mismatch")
                content = b"".join(chunks)
                kind, parseable = _kind(relative, content)
                files[relative] = content
                inventory.append({"path": relative, "size": actual_file, "sha256": digest.hexdigest(),
                                  "kind": kind, "hidden": any(part.startswith(".") for part in relative.split("/")),
                                  "executable": bool((info.external_attr >> 16) & 0o111),
                                  "parseable": parseable})
            return ImportedArchive(files, sorted(inventory, key=lambda item: item["path"]), root_name,
                                   hashlib.sha256(data).hexdigest())
    except PlatformError:
        raise
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, ValueError, EOFError, struct.error):
        _invalid("malformed_zip")
