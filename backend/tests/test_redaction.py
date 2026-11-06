import pytest

from backend.app.core.redaction import redact
from backend.app.scan.contracts import Finding


@pytest.mark.parametrize("variable", ["api_key", "token", "access_token", "client_secret", "password", "MY_TOKEN"])
def test_all_suspected_assignment_forms_redact(variable):
    secret = "SyntheticRandomValue321Abc567Def"
    assert secret not in redact(f'{variable} = "{secret}"')


def test_redaction_precedes_fingerprint_and_limits():
    def finding(secret):
        return Finding(rule_id="SQSP-S003", category="code", severity="HIGH", file_path="x.py",
                       evidence_excerpt=f"exec(value); token = '{secret}'", message="Review", remediation="Avoid").safe()
    first, second = finding("SyntheticSecret123456"), finding("OtherSyntheticSecret654321")
    assert first.fingerprint == second.fingerprint
    assert "SyntheticSecret" not in first.evidence_excerpt
