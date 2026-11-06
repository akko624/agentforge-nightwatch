"""Deterministic documentation checks; never estimates actual task success.

Only the conformance and maintainability dimensions are measured here. Neither
the completeness of prose nor the presence of eval fixtures proves that a host
selected the Skill or completed a real task.
"""

import re

from backend.app.scan.contracts import ScanContext

RUNNER_VERSION = "static-quality-1.0"


def _check(check_id: str, passed: bool, category: str, evidence_ref: str, label: str) -> dict:
    # References and labels are application constants, never source excerpts.
    return {"id": check_id, "passed": bool(passed), "category": category,
            "evidence_ref": evidence_ref, "label": label}


def _measured_dimension(name: str, weight: float, checks: list[dict], reason: str) -> dict:
    numerator = sum(check["passed"] for check in checks)
    denominator = len(checks)
    return {"dimension": name, "weight": weight,
            "status": "PASSED" if numerator == denominator else "FINDINGS",
            "score": round(100 * numerator / denominator, 2),
            "metric": "deterministic_checks_passed", "numerator": numerator, "denominator": denominator,
            "checks": checks, "reason": reason, "runner_version": RUNNER_VERSION,
            "evidence_ref": "SKILL.md"}


def _unmeasured_dimension(name: str, weight: float, metric: str, reason: str) -> dict:
    return {"dimension": name, "weight": weight, "status": "NOT_RUN", "score": None,
            "metric": metric, "numerator": None, "denominator": None, "checks": [],
            "reason": reason, "runner_version": None, "evidence_ref": None}


def _has_assertions(case: dict) -> bool:
    expected = case.get("expected", {})
    return bool(expected.get("output_file") or expected.get("contains")
                or expected.get("forbidden_tool_calls")
                or isinstance(expected.get("skill_selected"), bool))


def evaluate_static_quality(context: ScanContext) -> dict:
    """Measure 40% of the fixed model and retain null for complete quality.

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
    dimensions = [
        _measured_dimension("conformance", 0.2, conformance_checks,
                            "Official field validation and package reference checks; optional SQSP recommendations are scored separately."),
        _measured_dimension("maintainability", 0.2, maintainability_checks,
                            "Deterministic documentation heuristics only; keywords and declared fixtures do not demonstrate usability or task success."),
        _unmeasured_dimension("correctness", 0.4, "observed_host_task_outcomes",
                              "No approved real host runner is configured; selection, task success and baseline benefit were not measured."),
        _unmeasured_dimension("reliability", 0.2, "observed_repeated_run_efficiency",
                              "No approved repeated host runs are available; stability, latency, token and resource efficiency were not measured."),
    ]
    coverage = round(sum(dimension["weight"] for dimension in dimensions
                         if dimension["status"] in {"PASSED", "FINDINGS"}), 2)
    static_subscore = round((dimensions[0]["score"] + dimensions[1]["score"]) / 2, 2)
    return {"score": None, "coverage": coverage, "static_subscore": static_subscore,
            "dimensions": dimensions,
            "reasons": ["Full quality is unavailable: correctness and reliability have not been measured.",
                        "Static subscore covers only the two static dimensions; it is not the complete weighted quality score.",
                        "Documentation and test declarations were inspected without executing Skill code."]}
