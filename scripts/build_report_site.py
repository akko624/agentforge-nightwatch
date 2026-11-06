"""Package a static report viewer, optionally embedding an allowlisted summary.

Never uploads, deploys, executes a Skill, or copies a full report to the output.
Build the viewer first with `npm run build:report` in frontend.
"""
import argparse
import json
import math
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 5 * 1024 * 1024
LEVELS = ("critical", "high", "medium", "low", "info")
DIMENSIONS = {"conformance": 0.2, "maintainability": 0.2, "correctness": 0.4, "reliability": 0.2}
STAGES = {"schema", "static", "dependencies", "semantic", "dynamic", "quality"}
STATES = {"NOT_RUN", "RUNNING", "PASSED", "FINDINGS", "PARTIAL", "ERROR", "TIMEOUT", "UNAVAILABLE"}
CATEGORIES = {"credential-exfiltration", "remote-code-execution", "dangerous-execution", "unsupported-payload", "prompt-injection", "sensitive-filesystem", "plaintext-secret", "mutable-instructions", "permission-conflict", "path-traversal", "dependency-coverage", "install-hook", "high-impact-action", "overbroad-permissions", "maintainability", "conformance", "other"}
RULES = {f"SQSP-S{number:03d}" for number in range(1, 17)} | {"SQSP-C001", "OTHER"}


def number(value, maximum=100, integer=False):
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or not 0 <= value <= maximum or integer and int(value) != value:
        raise ValueError("Invalid numeric report field")
    return value


def enum(value, allowed):
    if not isinstance(value, str) or value not in allowed:
        raise ValueError("Unsupported report enum")
    return value


def read_json(path: Path) -> dict:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Report exceeds 5 MiB")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    data = json.loads(path.read_text("utf-8"), object_pairs_hook=unique_pairs)
    if not isinstance(data, dict):
        raise ValueError("Report must be a JSON object")
    return data


def validate_summary(data: dict) -> dict:
    """Accept only the exact public contract; arbitrary source text is forbidden."""
    if set(data) != {"schema_version", "scope", "status", "file_count", "severity_counts", "category_counts", "rule_counts", "stages", "quality", "security_verdict", "security_risk_index", "release_decision"}:
        raise ValueError("Public summary contains missing or non-public fields")
    if data["schema_version"] != "sqsp-public-1.0" or data["scope"] != "AGGREGATE_ONLY":
        raise ValueError("Unsupported public summary version")
    enum(data["status"], {"PARTIAL", "COMPLETED"})
    enum(data["security_verdict"], {"PASS", "REVIEW", "BLOCK", "UNKNOWN"})
    enum(data["release_decision"], {"ALLOW", "REVIEW", "BLOCK", "INCOMPLETE"})
    number(data["file_count"], 300, True)
    number(data["security_risk_index"])
    severity = data["severity_counts"]
    if not isinstance(severity, dict) or set(severity) != set(LEVELS):
        raise ValueError("Invalid severity counts")
    total = sum(number(value, 2000, True) for value in severity.values())
    number(total, 2000, True)
    for key, allowed in (("category_counts", CATEGORIES), ("rule_counts", RULES)):
        rows = data[key]
        if not isinstance(rows, dict) or not set(rows) <= allowed or sum(number(v, 2000, True) for v in rows.values()) != total:
            raise ValueError("Inconsistent public aggregate counts")
    stages = data["stages"]
    if not isinstance(stages, dict) or not {"schema", "static", "quality"} <= stages.keys() or not stages.keys() <= STAGES:
        raise ValueError("Invalid stage coverage")
    for stage in stages.values():
        if not isinstance(stage, dict) or set(stage) != {"status", "reason", "duration_ms", "coverage"} or stage["reason"] is not None or stage["coverage"] != {}:
            raise ValueError("Public stage must not contain source text")
        enum(stage["status"], STATES)
        number(stage["duration_ms"], 86_400_000, True)
    quality = data["quality"]
    if not isinstance(quality, dict) or set(quality) != {"score", "coverage", "static_subscore", "dimensions", "reasons"} or quality["reasons"] != []:
        raise ValueError("Invalid public quality fields")
    for key in ("score", "static_subscore"):
        if quality[key] is not None:
            number(quality[key])
    number(quality["coverage"], 1)
    dimensions = quality["dimensions"]
    if not isinstance(dimensions, list) or len(dimensions) != 4:
        raise ValueError("Four quality dimensions required")
    names, observed = set(), 0.0
    for dimension in dimensions:
        if not isinstance(dimension, dict) or set(dimension) != {"dimension", "weight", "status", "score"}:
            raise ValueError("Invalid public quality dimension")
        name = enum(dimension["dimension"], DIMENSIONS)
        names.add(name)
        if dimension["weight"] != DIMENSIONS[name]:
            raise ValueError("Invalid dimension weight")
        state = enum(dimension["status"], STATES)
        if dimension["score"] is not None:
            number(dimension["score"])
            if state not in {"PASSED", "FINDINGS"}:
                raise ValueError("Unmeasured dimension cannot have a score")
            observed += DIMENSIONS[name]
    if len(names) != 4 or abs(observed - quality["coverage"]) > 0.0001 or quality["score"] is not None and observed < 0.9999:
        raise ValueError("Quality coverage is inconsistent")
    static = [d for d in dimensions if d["dimension"] in {"conformance", "maintainability"}]
    if quality["static_subscore"] is not None and (any(d["score"] is None for d in static) or abs(quality["static_subscore"] - sum(d["score"] or 0 for d in static) / 2) > 0.011):
        raise ValueError("Static score is unsupported by measured dimensions")
    if quality["score"] is not None and abs(quality["score"] - sum((d["score"] or 0) * d["weight"] for d in dimensions)) > 0.011:
        raise ValueError("Full quality score differs from weighted dimensions")
    return data


def public_summary(report: dict) -> dict:
    if report.get("schema_version") == "sqsp-public-1.0":
        return validate_summary(report)
    if report.get("schema_version") != "1.0":
        raise ValueError("Unsupported report version")
    security, quality = report["security"], report["quality"]
    findings = security["findings"]
    if not isinstance(findings, list) or len(findings) > 2000:
        raise ValueError("Invalid findings")
    severities, categories, rules = dict.fromkeys(LEVELS, 0), {}, {}
    for finding in findings:
        severity = enum(finding["severity"], {level.upper() for level in LEVELS}).lower()
        severities[severity] += 1
        category = finding["category"] if finding["category"] in CATEGORIES else "other"
        rule = finding["rule_id"] if finding["rule_id"] in RULES else "OTHER"
        categories[category] = categories.get(category, 0) + 1
        rules[rule] = rules.get(rule, 0) + 1
    if severities != security["finding_counts"]:
        raise ValueError("Finding counts are inconsistent")
    # Deliberately construct a new allowlisted tree; never copy source metadata.
    summary = {
        "schema_version": "sqsp-public-1.0", "scope": "AGGREGATE_ONLY", "status": report["scan"]["status"],
        "file_count": report["artifact"]["files"], "severity_counts": severities, "category_counts": categories, "rule_counts": rules,
        "stages": {engine["name"]: {"status": engine["status"], "duration_ms": engine["duration_ms"], "reason": None, "coverage": {}}
                   for engine in report["engines"]},
        "quality": {"score": quality["score"], "coverage": quality["coverage"], "static_subscore": quality["static_subscore"],
                    "dimensions": [{key: row[key] for key in ("dimension", "weight", "status", "score")} for row in quality["dimensions"]], "reasons": []},
        "security_verdict": security["verdict"], "security_risk_index": security["risk_index"], "release_decision": report["decision"]["status"],
    }
    return validate_summary(summary)


def package_site(build: Path, output: Path, summary: dict | None = None) -> None:
    build, output = build.resolve(), output.resolve()
    if not (build / "index.html").is_file() or not (build / "assets").is_dir():
        raise ValueError("Build missing; run npm run build:report first")
    if output.exists():
        raise ValueError("Output must be a new directory; existing files are never overwritten")
    if output == build or output.is_relative_to(build) or build.is_relative_to(output):
        raise ValueError("Output must not overlap the build directory")
    if summary is not None:
        validate_summary(summary)
    for path in build.rglob("*"):
        if path.is_symlink():
            raise ValueError("Build must not contain symbolic links")
        if path.is_file() and path.relative_to(build).as_posix() != "index.html":
            if not path.is_relative_to(build / "assets") or path.suffix not in {".js", ".css", ".woff", ".woff2", ".ttf", ".svg", ".png"}:
                raise ValueError("Only built viewer assets may be packaged")
    html = (build / "index.html").read_text("utf-8")
    if html.count('<div id="root"></div>') != 1 or 'id="sqsp-public-summary"' in html:
        raise ValueError("Expected an unmodified standalone viewer build")
    shutil.copytree(build, output)
    if summary is not None:
        payload = json.dumps(summary, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("&", "\\u0026")
        html = html.replace('<div id="root"></div>', f'<script id="sqsp-public-summary" type="application/json">{payload}</script>\n<div id="root"></div>', 1)
        (output / "index.html").write_text(html, encoding="utf-8")
    (output / "_headers").write_text("/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: no-referrer\n  X-Frame-Options: DENY\n  Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Package a static viewer or an aggregate-only report snapshot; no deployment")
    parser.add_argument("--report", type=Path, help="Locally exported private report or an approved public summary")
    parser.add_argument("--build", type=Path, default=ROOT / "frontend/dist-report")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = public_summary(read_json(args.report)) if args.report else None
        package_site(args.build, args.output, summary)
    except (ValueError, KeyError, TypeError, OSError, RecursionError):
        parser.exit(1, "Invalid report, missing build, or nonempty/unsafe output; nothing was published.\n")
    print(args.output.resolve())
    print("Contains aggregate summary only; review before publishing." if summary else "Viewer only; visitors select their own local JSON.")


if __name__ == "__main__":
    main()
