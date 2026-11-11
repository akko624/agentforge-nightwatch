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


def test_all_dimensions_receive_static_verifiability_checks_without_runtime_score():
    result = evaluate_static_quality(minimal_context())
    assert result["score"] is None
    assert result["coverage"] == 1
    assert result["runtime_coverage"] == 0
    assert [item["weight"] for item in result["dimensions"]] == [0.2, 0.2, 0.4, 0.2]
    assert sum(item["weight"] for item in result["dimensions"]) == 1
    for dimension in result["dimensions"]:
        assert dimension["score"] is not None
        assert dimension["numerator"] is not None
        assert dimension["denominator"]
        assert dimension["runner_version"] == "static-quality-1.1"
        assert dimension["evidence_level"] == "STATIC_VERIFIABILITY"
    for dimension in result["dimensions"][2:]:
        assert dimension["runtime_status"] == "UNAVAILABLE"
        assert dimension["runtime_reason"]


def test_missing_recommendations_do_not_break_official_conformance():
    result = evaluate_static_quality(minimal_context())
    conformance, maintainability = result["dimensions"][:2]
    assert conformance["score"] == 100
    assert conformance["status"] == "PASSED"
    assert maintainability["score"] == 0
    assert maintainability["status"] == "FINDINGS"
    assert result["static_subscore"] == 20
    assert all(check["category"] == "platform_recommendation" for check in maintainability["checks"])


def test_complete_example_improves_static_subscore_without_full_runtime_quality():
    archive = read_archive(package_directory(ROOT / "examples/benign-skill"), Settings())
    result = evaluate_static_quality(ScanContext(archive.files, archive.inventory,
                                               parse_skill(archive.files, archive.root_name)))
    assert result["static_subscore"] == 72
    assert result["dimensions"][1]["numerator"] == result["dimensions"][1]["denominator"] == 9
    assert result["score"] is None
    assert result["coverage"] == 1
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
    assert result["dimensions"][2]["numerator"] == 0


def test_empty_case_is_not_a_verifiable_test_and_negative_selection_is():
    base = "schema_version: '1.0'\ncases:\n- id: x\n  name: test\n  category: trigger_negative\n  trigger_prompt: unrelated\n"
    empty = evaluate_static_quality(minimal_context(additional={"evals/cases.yaml": (base + "  expected: {}\n").encode()}))
    negative = evaluate_static_quality(minimal_context(additional={"evals/cases.yaml": (base + "  expected:\n    skill_selected: false\n").encode()}))
    assert empty["dimensions"][1]["checks"][6]["passed"] is False
    assert negative["dimensions"][1]["checks"][6]["passed"] is True
    assert negative["dimensions"][2]["score"] is not None


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


def test_correctness_and_reliability_static_checks_identify_complete_declarations():
    body = "# 用途\n## 输入和输出\n1. 执行任务。\n2. 输出结果。\n## 失败处理\n超时时重试一次，失败后降级；重复执行保持幂等，资源上限为 100 token。\n"
    cases = ("schema_version: '1.0'\n"
             "cases:\n"
             "- id: positive\n  name: 正常请求\n  category: trigger_positive\n  trigger_prompt: 正常输入\n  expected:\n    skill_selected: true\n"
             "- id: negative\n  name: 无关请求\n  category: trigger_negative\n  trigger_prompt: 无关输入\n  expected:\n    skill_selected: false\n"
             "- id: functional\n  name: 空输入边界\n  category: functional\n  trigger_prompt: 空输入\n  expected:\n    contains: ['错误']\n"
             "- id: stable\n  name: 重复稳定性\n  category: reliability\n  trigger_prompt: 正常输入\n  repeat: 2\n  expected:\n    contains: ['完成']\n").encode()
    result = evaluate_static_quality(minimal_context(body, additional={"evals/cases.yaml": cases}))
    correctness, reliability = result["dimensions"][2:]
    assert correctness["score"] == 100
    assert reliability["score"] == 80
    assert correctness["runtime_status"] == reliability["runtime_status"] == "UNAVAILABLE"
