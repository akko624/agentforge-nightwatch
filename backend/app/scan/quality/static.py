"""Deterministic, non-executing quality checks.

Every quality dimension receives a static *verifiability* check so an author
can improve the package before a trusted runner exists.  These checks inspect
only declarations and documentation.  They never estimate real task success,
stability, latency, or resource consumption.
"""

import re

from backend.app.scan.contracts import ScanContext

RUNNER_VERSION = "static-quality-1.1"


def _check(check_id: str, passed: bool, category: str, evidence_ref: str, label: str) -> dict:
    # References and labels are application constants, never source excerpts.
    return {"id": check_id, "passed": bool(passed), "category": category,
            "evidence_ref": evidence_ref, "label": label}


def _measured_dimension(name: str, weight: float, checks: list[dict], reason: str,
                        *, runtime_status: str = "NOT_APPLICABLE", runtime_reason: str | None = None) -> dict:
    numerator = sum(check["passed"] for check in checks)
    denominator = len(checks)
    return {"dimension": name, "weight": weight,
            "status": "PASSED" if numerator == denominator else "FINDINGS",
            "score": round(100 * numerator / denominator, 2),
            "metric": "deterministic_checks_passed", "numerator": numerator, "denominator": denominator,
            "checks": checks, "reason": reason, "runner_version": RUNNER_VERSION,
            "evidence_ref": "package declarations", "evidence_level": "STATIC_VERIFIABILITY",
            "runtime_status": runtime_status, "runtime_reason": runtime_reason}


def _has_assertions(case: dict) -> bool:
    expected = case.get("expected", {})
    return bool(expected.get("output_file") or expected.get("contains")
                or expected.get("forbidden_tool_calls")
                or isinstance(expected.get("skill_selected"), bool))


def _case_assertion_is_complete(case: dict) -> bool:
    """Require a task case to state an observable result without executing it."""
    expected = case.get("expected", {})
    if not isinstance(expected, dict) or not _has_assertions(case):
        return False
    category = case.get("category")
    if category == "trigger_negative":
        return expected.get("skill_selected") is False
    if category == "trigger_positive":
        return expected.get("skill_selected") is True
    return bool(expected.get("output_file") or expected.get("contains") or expected.get("forbidden_tool_calls"))


def _has_boundary_case(cases: list[dict]) -> bool:
    boundary = re.compile(r"\b(?:empty|missing|invalid|malformed|error|fail|timeout|limit|boundary)\b|为空|缺失|无效|异常|错误|失败|超时|边界|上限", re.I)
    return any(boundary.search(" ".join(str(case.get(key, "")) for key in ("id", "name", "trigger_prompt")))
               for case in cases)


def _has_terms(text: str, expression: str) -> bool:
    return re.search(expression, text, re.I) is not None


def evaluate_static_quality(context: ScanContext) -> dict:
    """Check all fixed dimensions statically and retain null for runtime quality.

    The caller must supply the ParsedSkill produced by the safe parser. Invalid
    mandatory frontmatter is rejected at ingestion; local reference issues may
    remain and reduce conformance. Platform recommendations do not masquerade as
    official mandatory fields.
    """
    parsed = context.parsed
    frontmatter, body = parsed.frontmatter, parsed.body
    name, description = frontmatter.get("name", ""), frontmatter.get("description", "")
    metadata = frontmatter.get("metadata", {})
    valid_metadata = isinstance(metadata, dict) and all(
        isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()
    )
    valid_optional = valid_metadata and all(
        field not in frontmatter or isinstance(frontmatter[field], str)
        for field in ("license", "compatibility", "allowed-tools")
    )
    valid_optional = valid_optional and len(frontmatter.get("compatibility", "")) <= 500
    conformance_checks = [
        _check("official_name", isinstance(name, str) and len(name) <= 64
               and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is not None,
               "official_required", "SKILL.md#frontmatter", "Official name constraints"),
        _check("official_description", isinstance(description, str) and bool(description.strip())
               and len(description) <= 1024, "official_required", "SKILL.md#frontmatter",
               "Official description constraints"),
        _check("official_optional_fields", valid_optional, "official_optional", "SKILL.md#frontmatter",
               "Present optional frontmatter fields have valid types and limits"),
        _check("package_reference_integrity", not parsed.issues, "package_integrity", "manifest.issues",
               "Local resource references resolve inside this package"),
    ]
    description_has_purpose = len(description.strip()) >= 32 and re.search(
        r"\bwhen\b|\buse\s+(?:for|to)\b|适用|用于|当.{0,40}时", description, re.I,
    ) is not None
    has_example = re.search(
        r"(?im)^#{1,6}[ \t]+[^\n]*(?:\bexamples?\b|示例|例子)|^[ \t]*(?:examples?|示例|例子)[ \t]*[:：]",
        body,
    ) is not None
    steps = re.findall(r"(?m)^[ \t]*(?:\d+[.)]|[一二三四五六七八九十]+[、.])[ \t]*\S", body)
    maintainability_checks = [
        _check("purpose", description_has_purpose or re.search(r"\b(?:purpose|overview|goal|scope)\b|用途|目的|范围|目标", body, re.I),
               "platform_recommendation", "SKILL.md", "Purpose and intended use are described"),
        _check("inputs", re.search(r"\binputs?\b|输入", body, re.I),
               "platform_recommendation", "SKILL.md", "Input requirements are described"),
        _check("outputs", re.search(r"\boutputs?\b|输出|产物", body, re.I),
               "platform_recommendation", "SKILL.md", "Expected outputs are described"),
        _check("ordered_steps", len(steps) >= 2, "platform_recommendation", "SKILL.md",
               "At least two ordered workflow steps are present"),
        _check("failure_handling", re.search(r"\b(?:errors?|fails?|failed|failure|invalid|timeout|unavailable|retry|exceptions?)\b|失败|错误|异常|超时|重试|无效|缺失|无法", body, re.I),
               "platform_recommendation", "SKILL.md", "Failure or invalid-input handling is described"),
        _check("example", has_example, "platform_recommendation", "SKILL.md", "An example section is present"),
        _check("declared_test_assertions", any(_has_assertions(case) for case in parsed.evals.get("cases", [])),
               "platform_recommendation", "evals/cases.yaml", "A parsed test case declares an observable assertion"),
        _check("license", bool(frontmatter.get("license", "").strip()) or any(
            path.rsplit("/", 1)[-1].lower() in {"license", "license.txt", "license.md", "copying"}
            for path in context.files), "platform_recommendation", "SKILL.md#frontmatter", "A license is declared"),
        _check("version", bool(metadata.get("version", "").strip()) if valid_metadata else False,
               "platform_recommendation", "SKILL.md#frontmatter", "An author-declared version label is present"),
    ]
    cases = parsed.evals.get("cases", [])
    functional_cases = [case for case in cases if case.get("category") == "functional"]
    positive_cases = [case for case in cases if case.get("category") == "trigger_positive"]
    negative_cases = [case for case in cases if case.get("category") == "trigger_negative"]
    reliability_cases = [case for case in cases if case.get("category") == "reliability"]
    task_cases = [case for case in cases if case.get("category") in {"functional", "trigger_positive", "trigger_negative"}]
    correctness_checks = [
        _check("functional_case", bool(functional_cases), "static_verifiability", "evals/cases.yaml",
               "已声明至少一个功能用例"),
        _check("positive_trigger_case", bool(positive_cases) or bool(functional_cases), "static_verifiability", "evals/cases.yaml",
               "已声明正向触发或功能用例"),
        _check("negative_trigger_case", any(case.get("expected", {}).get("skill_selected") is False for case in negative_cases),
               "static_verifiability", "evals/cases.yaml", "已声明不应触发 Skill 的反向用例"),
        _check("observable_task_assertions", bool(task_cases) and all(_case_assertion_is_complete(case) for case in task_cases),
               "static_verifiability", "evals/cases.yaml", "每个任务用例都定义了可观察预期"),
        _check("boundary_case", _has_boundary_case(cases), "static_verifiability", "evals/cases.yaml",
               "已声明输入或失败边界用例"),
    ]
    reliability_checks = [
        _check("repeated_reliability_case", any(case.get("repeat", 1) >= 2 for case in reliability_cases),
               "static_verifiability", "evals/cases.yaml", "已声明至少一个重复执行的稳定性用例"),
        _check("timeout_or_budget", _has_terms(body, r"\b(?:timeout|time\s*limit|budget|token(?:s)?\s*(?:limit|budget)|resource\s*limit)\b|超时|时限|时间限制|预算|令牌上限|资源上限"),
               "static_verifiability", "SKILL.md", "已声明超时或资源预算边界"),
        _check("retry_or_recovery", _has_terms(body, r"\b(?:retry|recovery|recover|fallback)\b|重试|恢复|降级|回退"),
               "static_verifiability", "SKILL.md", "已声明重试、恢复或降级策略"),
        _check("idempotency", _has_terms(body, r"\b(?:idempot(?:ent|ency)|repeatable|deterministic)\b|幂等|可重复|确定性"),
               "static_verifiability", "SKILL.md", "已说明重复执行的一致性或幂等性"),
        _check("dependency_failure_contract", _has_terms(body, r"\b(?:dependency|dependencies|tool|network|service)\b.{0,120}\b(?:error|fail|timeout|unavailable|retry)\b|(?:依赖|工具|网络|服务).{0,120}(?:失败|错误|超时|不可用|重试)"),
               "static_verifiability", "SKILL.md", "已说明外部依赖失败时的处理"),
    ]
    runtime_unavailable = "未接入可信隔离 Runner：未执行上传代码，不能证明真实任务成功、稳定性、延迟或资源消耗。"
    dimensions = [
        _measured_dimension("conformance", 0.2, conformance_checks,
                            "Official field validation and package reference checks; optional SQSP recommendations are scored separately."),
        _measured_dimension("maintainability", 0.2, maintainability_checks,
                            "Deterministic documentation heuristics only; keywords and declared fixtures do not demonstrate usability or task success."),
        _measured_dimension("correctness", 0.4, correctness_checks,
                            "静态可验证性检查：核对功能、触发、反向触发、断言与边界用例的声明；不代表功能已真实执行。",
                            runtime_status="UNAVAILABLE", runtime_reason=runtime_unavailable),
        _measured_dimension("reliability", 0.2, reliability_checks,
                            "静态可验证性检查：核对重复用例、时限、恢复、幂等与依赖失败约定；不代表稳定性或效率已真实测量。",
                            runtime_status="UNAVAILABLE", runtime_reason=runtime_unavailable),
    ]
    coverage = round(sum(dimension["weight"] for dimension in dimensions
                         if dimension["status"] in {"PASSED", "FINDINGS"}), 2)
    static_subscore = round(sum(dimension["weight"] * dimension["score"] for dimension in dimensions), 2)
    return {"score": None, "coverage": coverage, "runtime_coverage": 0.0, "static_subscore": static_subscore,
            "dimensions": dimensions,
            "reasons": ["四个维度均完成静态可验证性检查；这不是四个维度的真实运行时评测。",
                        "完整质量分保持未评测：功能正确性、触发率、稳定性、延迟、令牌与资源效率均未在可信隔离环境中观测。",
                        "所有检查只读取文档与评测声明，未执行、导入或调用上传 Skill 的代码。"]}
