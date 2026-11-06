from backend.app.core.errors import PlatformError
from backend.app.skill.parser import load_yaml

STAGES = {"schema", "static", "dependencies", "semantic", "dynamic", "quality"}


def load_policy(path) -> dict:
    policy = load_yaml(path.read_bytes(), code="INVALID_POLICY")
    if not isinstance(policy, dict) or not isinstance(policy.get("version"), str):
        raise PlatformError("INVALID_POLICY", "Invalid policy configuration", 500)
    required = policy.get("required_stages")
    if not isinstance(required, list) or not set(required) <= STAGES or not {"schema", "static"} <= set(required):
        raise PlatformError("INVALID_POLICY", "Schema and static stages must be required", 500)
    if not isinstance(policy.get("require_full_quality", False), bool):
        raise PlatformError("INVALID_POLICY", "require_full_quality must be boolean", 500)
    if policy.get("require_full_quality") and "quality" not in required:
        policy["required_stages"] = [*required, "quality"]
    return policy


def decide(findings, stages: dict, policy: dict, modes: list[str]) -> dict:
    weights = {"INFO": 0, "LOW": 2, "MEDIUM": 8, "HIGH": 20, "CRITICAL": 50}
    factors = {"LOW": 0.3, "MEDIUM": 0.7, "HIGH": 1.0}
    active = [f for f in findings if f.status == "OPEN"]
    risk = min(100.0, sum(weights[f.severity] * factors[f.confidence] for f in active))
    critical = any(f.severity == "CRITICAL" and f.confidence == "HIGH" and not f.context_note for f in active)
    unsafe_parse = any(f.rule_id == "SQSP-C001" and "UNSAFE_REFERENCE" in f.message for f in active)
    review = any(f.severity in {"MEDIUM", "HIGH", "CRITICAL"} for f in active)
    required = set(policy["required_stages"]) | set(modes)
    if policy.get("require_full_quality"):
        required.add("quality")
    incomplete = [name for name in sorted(required) if stages[name]["status"] not in {"PASSED", "FINDINGS"}]
    if policy.get("require_full_quality") and stages["quality"].get("coverage", {}).get("quality_coverage", 0) < 1 and "quality" not in incomplete:
        incomplete.append("quality")
    if critical or unsafe_parse:
        verdict, decision = "BLOCK", "BLOCK"
        reasons = ["confirmed_critical_evidence" if critical else "unsafe_package_reference"]
    elif incomplete:
        verdict, decision = ("REVIEW" if review else "UNKNOWN"), "INCOMPLETE"
        reasons = [f"{stage}:{stages[stage]['status']}" for stage in incomplete]
    elif review:
        verdict, decision = "REVIEW", "REVIEW"
        reasons = ["findings_require_human_review"]
    else:
        verdict, decision = "PASS", "ALLOW"
        reasons = ["configured_static_gate_only"]
    return {"security_verdict": verdict, "release_decision": decision, "security_risk_index": risk,
            "reasons": reasons, "required_stages": sorted(required),
            "scope": "Configured checks only; not a comprehensive safety guarantee"}
