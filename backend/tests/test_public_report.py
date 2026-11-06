import json

import pytest

from scripts.build_report_site import package_site, public_summary, read_json, validate_summary


def private_report():
    return {
        "schema_version": "1.0", "scan": {"status": "PARTIAL", "id": "private-scan-id"},
        "artifact": {"files": 1, "name": "private-customer-skill", "inventory": [{"path": "private.py"}]},
        "security": {"verdict": "REVIEW", "risk_index": 20, "findings": [{"rule_id": "SQSP-S003", "category": "dangerous-execution", "severity": "HIGH", "evidence_excerpt": "private secret", "file_path": "private.py"}], "finding_counts": {"critical": 0, "high": 1, "medium": 0, "low": 0, "info": 0}},
        "quality": {"score": None, "coverage": 0.4, "static_subscore": 80, "dimensions": [
            {"dimension": name, "weight": weight, "status": "PASSED" if index < 2 else "NOT_RUN", "score": 80 if index < 2 else None}
            for index, (name, weight) in enumerate({"conformance": 0.2, "maintainability": 0.2, "correctness": 0.4, "reliability": 0.2}.items())]},
        "engines": [{"name": stage, "status": "PARTIAL" if stage == "quality" else "PASSED", "duration_ms": 1, "reason": "private-stage-reason"} for stage in ("schema", "static", "quality")],
        "decision": {"status": "INCOMPLETE"}, "permissions": {"private": "host-path"},
    }


def test_public_projection_drops_all_source_text_and_identifiers():
    summary = public_summary(private_report())
    assert "private" not in json.dumps(summary)
    assert "evidence_excerpt" not in json.dumps(summary)
    assert summary["severity_counts"]["high"] == 1
    assert summary["quality"]["score"] is None
    assert validate_summary(summary) == summary


def test_public_contract_rejects_extra_fields_and_inconsistent_counts():
    summary = public_summary(private_report())
    summary["source_name"] = "private"
    with pytest.raises(ValueError):
        validate_summary(summary)
    summary.pop("source_name")
    summary["severity_counts"]["high"] = 9
    with pytest.raises(ValueError):
        validate_summary(summary)


def test_snapshot_packages_only_aggregate_and_never_overwrites(tmp_path):
    build, output = tmp_path / "build", tmp_path / "site"
    (build / "assets").mkdir(parents=True)
    (build / "assets/viewer.js").write_text("console.log('viewer')", "utf-8")
    (build / "index.html").write_text('<div id="root"></div>', "utf-8")
    package_site(build, output, public_summary(private_report()))
    html = (output / "index.html").read_text("utf-8")
    assert 'id="sqsp-public-summary"' in html
    assert "private" not in html
    assert "connect-src 'none'" in (output / "_headers").read_text("utf-8")
    with pytest.raises(ValueError):
        package_site(build, output)


def test_snapshot_refuses_accidentally_bundled_private_report(tmp_path):
    build = tmp_path / "build"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text('<div id="root"></div>', "utf-8")
    (build / "private-report.json").write_text(json.dumps(private_report()), "utf-8")
    with pytest.raises(ValueError):
        package_site(build, tmp_path / "site")


def test_json_input_rejects_duplicate_fields(tmp_path):
    path = tmp_path / "report.json"
    path.write_text('{"schema_version":"1.0","schema_version":"bad"}', "utf-8")
    with pytest.raises(ValueError):
        read_json(path)
