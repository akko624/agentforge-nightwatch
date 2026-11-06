import json

from backend.app.core.config import ROOT, Settings
from backend.app.ingest.safe_zip import read_archive
from backend.app.scan.contracts import ScanContext
from backend.app.scan.quality import evaluate_static_quality
from backend.app.skill.parser import parse_skill
from scripts.seed_examples import package_directory


def minimal_context(body="", extra="", additional=None):
    files = {"SKILL.md": ("---\nname: quality-test\ndescription: A helper.\n" + extra + "---\n" + body).encode()}
    files.update(additional or {})
    return ScanContext(files, [], parse_skill(files))


def test_only_completed_static_dimensions_contribute_coverage():
    result = evaluate_static_quality(minimal_context())
    assert result["score"] is None
    assert result["coverage"] == 0.4
    assert [item["weight"] for item in result["dimensions"]] == [0.2, 0.2, 0.4, 0.2]
    assert sum(item["weight"] for item in result["dimensions"]) == 1
    for dimension in result["dimensions"][2:]:
        assert dimension["status"] == "NOT_RUN"
        for missing in ("score", "numerator", "denominator", "runner_version", "evidence_ref"):
            assert dimension[missing] is None
        assert dimension["checks"] == []
        assert dimension["reason"]


def test_missing_recommendations_do_not_break_official_conformance():
    result = evaluate_static_quality(minimal_context())
    conformance, maintainability = result["dimensions"][:2]
    assert conformance["score"] == 100
    assert conformance["status"] == "PASSED"
    assert maintainability["score"] == 0
    assert maintainability["status"] == "FINDINGS"
    assert result["static_subscore"] == 50
    assert all(check["category"] == "platform_recommendation" for check in maintainability["checks"])


def test_complete_example_improves_local_subscore_without_full_quality():
    archive = read_archive(package_directory(ROOT / "examples/benign-skill"), Settings())
    result = evaluate_static_quality(ScanContext(archive.files, archive.inventory,
                                               parse_skill(archive.files, archive.root_name)))
    assert result["static_subscore"] == 100
    assert result["dimensions"][1]["numerator"] == result["dimensions"][1]["denominator"] == 9
    assert result["score"] is None
    assert result["coverage"] == 0.4
    assert result["reasons"]


def test_missing_or_escaping_references_reduce_conformance():
    result = evaluate_static_quality(minimal_context("[missing](references/missing.md)\n[escape](../../host.txt)"))
    conformance = result["dimensions"][0]
    assert conformance["score"] == 75
    assert conformance["numerator"] == 3
    assert conformance["denominator"] == 4
    assert conformance["checks"][-1]["passed"] is False


def test_chinese_prose_is_checked_without_claiming_task_execution():
    body = "# 用途\n## 输入和输出\n1. 读取输入文件。\n2. 生成输出。\n## 错误处理\n失败时停止。\n## 示例\n输入一行，预期输出摘要。"
    result = evaluate_static_quality(minimal_context(body))
    passed = {check["id"] for check in result["dimensions"][1]["checks"] if check["passed"]}
    assert {"purpose", "inputs", "outputs", "ordered_steps", "failure_handling", "example"} <= passed
    assert result["score"] is None
    assert result["dimensions"][2]["numerator"] is None


def test_empty_case_is_not_a_verifiable_test_and_negative_selection_is():
    base = "schema_version: '1.0'\ncases:\n- id: x\n  name: test\n  category: trigger_negative\n  trigger_prompt: unrelated\n"
    empty = evaluate_static_quality(minimal_context(additional={"evals/cases.yaml": (base + "  expected: {}\n").encode()}))
    negative = evaluate_static_quality(minimal_context(additional={"evals/cases.yaml": (base + "  expected:\n    skill_selected: false\n").encode()}))
    assert empty["dimensions"][1]["checks"][6]["passed"] is False
    assert negative["dimensions"][1]["checks"][6]["passed"] is True
    assert negative["dimensions"][2]["score"] is None


def test_quality_evidence_does_not_include_source_or_secret_values():
    synthetic_secret = "sk-QualityFixtureOnly0123456789abcdefghijklmnopqrstuv"
    context = minimal_context("# Example\nInput and output: " + synthetic_secret,
                              extra=f"license: '{synthetic_secret}'\nmetadata:\n  version: '{synthetic_secret}'\n")
    serialized = json.dumps(evaluate_static_quality(context))
    assert synthetic_secret not in serialized
    assert "QualityFixtureOnly" not in serialized
    assert "SKILL.md" in serialized


def test_scoring_is_reproducible():
    context = minimal_context("# Purpose\nInputs: a file.\nOutput: a summary.\n1. Read.\n2. Summarize.\nError: stop.")
    assert evaluate_static_quality(context) == evaluate_static_quality(context)
