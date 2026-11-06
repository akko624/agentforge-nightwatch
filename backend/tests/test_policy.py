import pytest

from backend.app.core.errors import PlatformError
from backend.app.policy.decision import decide, load_policy
from backend.app.policy.permissions import permission_intersection
from backend.app.scan.contracts import Finding


def stages(**changes):
    result = {name: {"status": "PASSED"} for name in ("schema", "static", "quality", "dynamic", "semantic", "dependencies")}
    result.update({key: {"status": value} for key, value in changes.items()})
    return result


def candidate(severity="HIGH", **kwargs):
    return Finding(rule_id="SQSP-S001", category="exfiltration", severity=severity, confidence="HIGH",
                   file_path="scripts/x.py", message="candidate", remediation="Review", **kwargs).safe()


def test_decision_priority_and_explicit_gate():
    policy = {"required_stages": ["schema", "static"]}
    assert decide([], stages(), policy, ["static"])["release_decision"] == "ALLOW"
    assert decide([candidate()], stages(), policy, ["static"])["release_decision"] == "REVIEW"
    assert decide([candidate()], stages(static="ERROR"), policy, ["static"])["release_decision"] == "INCOMPLETE"
    assert decide([candidate("CRITICAL")], stages(static="ERROR"), policy, ["static"])["release_decision"] == "BLOCK"
    assert decide([candidate("CRITICAL", context_note="negative example")], stages(), policy, ["static"])["release_decision"] == "REVIEW"
    assert decide([], stages(dynamic="UNAVAILABLE"), policy, ["dynamic"])["release_decision"] == "INCOMPLETE"


def test_policy_configuration_cannot_disable_required_schema_static(tmp_path):
    policy = tmp_path / "policy.yaml"
    policy.write_text("version: '1.0'\nrequired_stages: [quality]", encoding="utf-8")
    with pytest.raises(PlatformError):
        load_policy(policy)


def test_full_quality_policy_requires_observed_complete_coverage():
    policy = {"required_stages": ["schema", "static"], "require_full_quality": True}
    result = decide([], stages(quality="NOT_RUN"), policy, ["schema", "static"])
    assert result["release_decision"] == "INCOMPLETE"
    assert "quality" in result["required_stages"]
    result = decide([], stages(), policy, ["schema", "static"])
    assert result["release_decision"] == "INCOMPLETE"
    complete = stages()
    complete["quality"]["coverage"] = {"quality_coverage": 1}
    assert decide([], complete, policy, ["schema", "static"])["release_decision"] == "ALLOW"


def test_permission_requests_never_grant_authority():
    declaration = {"security": {"network": {"mode": "allowlist", "allow_hosts": ["example.invalid"]},
                                "subprocess": {"allowed": True}, "environment": {"secret_access": True}}}
    result = permission_intersection(declaration, {"approved_permissions": {"network": "deny"}})
    assert result["effective"]["network"]["mode"] == "deny"
    assert result["effective"]["subprocess"] is False
    assert result["effective"]["secret_access"] is False
    assert result["execution_enforcement"] == "UNAVAILABLE"
    assert permission_intersection({}, {})["effective"]["filesystem"] == {"read": [], "write": []}


def test_conservative_path_and_host_intersection():
    declaration = {"security": {"network": {"mode": "allowlist", "allow_hosts": ["ok.invalid", "no.invalid"]},
                                "filesystem": {"read": ["${WORKSPACE}/inputs/x.csv", "${WORKSPACE}/**"]}}}
    policy = {"approved_permissions": {"network": "allowlist", "allow_hosts": ["ok.invalid"],
                                        "filesystem": {"read": ["${WORKSPACE}/inputs/**"]}}}
    effective = permission_intersection(declaration, policy)["effective"]
    assert effective["network"]["allow_hosts"] == ["ok.invalid"]
    assert effective["filesystem"]["read"] == ["${WORKSPACE}/inputs/x.csv"]
