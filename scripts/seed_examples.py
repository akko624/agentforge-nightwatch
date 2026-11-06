"""Create deterministic upload fixtures without importing/executing Skill code."""

import argparse
import io
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def package_directory(directory: Path, *, repaired: bool = False) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(directory.rglob("*")):
            if file.is_symlink():
                raise ValueError("Example source must not contain symlinks")
            if not file.is_file():
                continue
            content = file.read_bytes()
            relative = file.relative_to(directory).as_posix()
            if repaired:
                if relative == "scripts/payload.py":
                    # Repair exactly one AST risk; retain the rest for comparison.
                    content = content.replace(b"return eval(user_input)", b"return str(user_input)")
                elif relative == "SKILL.md":
                    content = content.replace(b'version: "1.0.0"', b'version: "1.0.1"')
            entry = zipfile.ZipInfo(f"{directory.name}/{relative}", date_time=(2026, 11, 3, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o444) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, content)
    return stream.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build safe synthetic SQSP upload fixtures")
    parser.add_argument("--output", type=Path, default=ROOT / "examples/zips")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name in ("benign-skill", "suspicious-skill"):
        output = args.output / f"{name}.zip"
        output.write_bytes(package_directory(ROOT / "examples" / name))
        print(output)
    repaired = args.output / "suspicious-skill-v2.zip"
    repaired.write_bytes(package_directory(ROOT / "examples/suspicious-skill", repaired=True))
    print(repaired)


if __name__ == "__main__":
    main()
