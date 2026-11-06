"""Create a portable SQSP Agent Skill ZIP without copying platform data or build output."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "agent_skills" / "skillforge-nightwatch"
ALLOWED = (Path("SKILL.md"), Path("agents/openai.yaml"), Path("scripts/scan_skill.py"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Package the SQSP Agent Skill wrapper; never includes reports, ZIPs, or runtime data")
    parser.add_argument("--output", type=Path, required=True, help="New .zip output path; existing files are refused")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.suffix.lower() != ".zip" or output.exists() or not output.parent.is_dir():
        parser.exit(1, "Output must be a new .zip file whose parent directory already exists.\n")
    missing = [path for path in ALLOWED if not (SKILL_ROOT / path).is_file()]
    if missing:
        parser.exit(1, "Skill source is incomplete; nothing was packaged.\n")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for relative in ALLOWED:
            bundle.write(SKILL_ROOT / relative, (Path("skillforge-nightwatch") / relative).as_posix())
    print(output)
    print("Contains only the agent wrapper; install it beside or point it at a trusted SQSP checkout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
