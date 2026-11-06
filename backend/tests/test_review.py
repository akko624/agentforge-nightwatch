"""Independent review regressions. All tokens and targets are synthetic."""

from datetime import timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.app.db.models import Scan, now
from backend.app.db.session import session_factory
from backend.app.scan.orchestrator import run_scan
from backend.tests.test_scans import create_job
from backend.tests.test_upload import archive_files


def test_review_findings_endpoint_redacts_secrets_in_file_paths(client):
    secret = "sk-ReviewSyntheticOnly0123456789abcdefghijklmnopqrstuvwxyz"
    files = {"SKILL.md": b"---\nname: review-skill\ndescription: Synthetic static fixture.\n---\n# Fixture\n",
             f"scripts/{secret}.py": b"eval(user_input)\n"}
    scan_id = create_job(client, archive_files(files))
    run_scan(scan_id)
    report = client.get(f"/api/v1/scans/{scan_id}/report")
    findings = client.get(f"/api/v1/scans/{scan_id}/findings")
    assert report.status_code == findings.status_code == 200
    assert secret not in report.text
    assert secret not in findings.text


def test_review_execution_provenance_matches_reusable_scan_signature(client, configured, tmp_path):
    # Use test-owned configuration copies; never mutate actual platform policy.
    rules_path, policy_path = tmp_path / "rules.yaml", tmp_path / "policy.yaml"
    original_rules = configured.rules_path.read_bytes()
    rules_path.write_bytes(original_rules)
    policy_path.write_bytes(configured.policy_path.read_bytes())
    configured.rules_path, configured.policy_path = rules_path, policy_path
    scan_id = create_job(client)
    # A configuration deployment between API enqueue and worker execution.
    rules_path.write_bytes(original_rules.replace(b"version: '1.0'", b"version: 'review-v2'", 1))
    run_scan(scan_id)
    summary = client.get(f"/api/v1/scans/{scan_id}").json()
    if summary["status"] == "FAILED":
        assert summary["release_decision"] == "INCOMPLETE"
        return  # Explicitly rejecting configuration drift is also safe.
    report = client.get(f"/api/v1/scans/{scan_id}/report").json()
    assert summary["scanner_versions"]["ruleset_sha256"] == report["provenance"]["ruleset_sha256"]


def test_review_fingerprint_does_not_depend_on_secret_in_filename():
    from backend.app.scan.contracts import Finding

    def item(secret):
        return Finding(rule_id="SQSP-S003", category="code", severity="HIGH",
                       file_path=f"scripts/{secret}.py", evidence_excerpt="eval(user_input)",
                       message="Review dynamic evaluation", remediation="Use a safe parser").safe()

    left = item("sk-FirstSyntheticSecretOnly0123456789abcdefghij")
    right = item("sk-SecondSyntheticSecretOnly9876543210zyxwvut")
    assert left.fingerprint == right.fingerprint


def test_review_report_signature_tracks_policy_change_before_execution(client, configured, tmp_path):
    rules_path, policy_path = tmp_path / "rules.yaml", tmp_path / "policy.yaml"
    rules_path.write_bytes(configured.rules_path.read_bytes())
    original_policy = configured.policy_path.read_bytes()
    policy_path.write_bytes(original_policy)
    configured.rules_path, configured.policy_path = rules_path, policy_path
    scan_id = create_job(client)
    policy_path.write_bytes(original_policy.replace(b'version: "1.0"', b'version: "review-v2"', 1))
    run_scan(scan_id)
    with session_factory()() as db:
        scan = db.get(Scan, scan_id)
        if scan.status == "FAILED":
            assert scan.release_decision == "INCOMPLETE"
            return
        import hashlib
        actual_policy_hash = hashlib.sha256(policy_path.read_bytes()).hexdigest()
        assert scan.scanner_versions["policy_sha256"] == actual_policy_hash


@pytest.mark.parametrize("queue_backend", ["database", "redis"])
def test_review_expired_cleanup_does_not_clobber_worker_completion(client, monkeypatch, queue_backend):
    from backend.app.scan.orchestrator import run_pending_scan

    scan_id = create_job(client)
    with session_factory()() as db:
        scan = db.get(Scan, scan_id)
        scan.status, scan.attempts, scan.lease_token = "RUNNING", 2, "synthetic-old-token"
        scan.lease_expires_at = now() - timedelta(seconds=1)
        db.commit()
    original_scalars = Session.scalars
    interleaved = False

    def select_before_concurrent_completion(session, statement, *args, **kwargs):
        nonlocal interleaved
        result = original_scalars(session, statement, *args, **kwargs)
        if interleaved or "scans.lease_expires_at <" not in str(statement):
            return result

        class ResultBeforeCompletion:
            def all(self):
                nonlocal interleaved
                rows = result.all()
                if rows:
                    interleaved = True
                    # Completion wins after SELECT and before cleanup's update.
                    with session_factory()() as winner:
                        winner.execute(update(Scan).where(Scan.id == scan_id).values(
                            status="PARTIAL", error_code=None, lease_token=None, lease_expires_at=None,
                            completed_at=now(), report_json={"scan": {"status": "PARTIAL"}},
                        ))
                        winner.commit()
                return rows

        return ResultBeforeCompletion()

    monkeypatch.setattr(Session, "scalars", select_before_concurrent_completion)
    if queue_backend == "database":
        run_pending_scan()
    else:
        import rq

        from backend.app.scan.queue import reconcile_redis_queue

        # Exhausted leases do not enqueue anything; Redis is irrelevant to this
        # race, so only replace the Queue constructor and keep real SQL logic.
        monkeypatch.setattr(rq, "Queue", lambda *args, **kwargs: None)
        reconcile_redis_queue(object())
    assert interleaved
    with session_factory()() as db:
        scan = db.get(Scan, scan_id)
        assert scan.status == "PARTIAL"
        assert scan.error_code is None


def test_review_effective_permissions_respect_explicit_declaration_deny():
    from backend.app.policy.permissions import permission_intersection

    path = "${WORKSPACE}/inputs/private.csv"
    declaration = {"security": {"filesystem": {"read": [path], "deny": [path]}}}
    policy = {"approved_permissions": {"filesystem": {"read": ["${WORKSPACE}/inputs/**"]}}}
    assert permission_intersection(declaration, policy)["effective"]["filesystem"]["read"] == []


def test_review_enqueue_ack_failure_cannot_overwrite_finished_scan(client, configured, monkeypatch):
    from rq import Queue

    configured.queue_backend = "redis"

    def enqueue_after_worker_completion(queue, function, scan_id, **kwargs):
        function(scan_id)  # Redis accepted the job and a worker already finished.
        raise TimeoutError("Synthetic lost Redis acknowledgement")

    monkeypatch.setattr(Queue, "enqueue", enqueue_after_worker_completion)
    from backend.tests.test_upload import upload, valid_zip
    version_id = upload(client, valid_zip()).json()["version_id"]
    response = client.post("/api/v1/scans", json={"version_id": version_id})
    body = response.json()
    scan_id = body.get("scan_id") or body["error"]["details"]["scan_id"]
    with session_factory()() as db:
        scan = db.get(Scan, scan_id)
        assert scan.status == "PARTIAL"
        assert scan.error_code is None


def test_review_scan_summary_redacts_secret_shaped_author_name(client):
    from backend.tests.test_upload import valid_zip

    # Lowercase secret-shaped strings can also be valid official Skill names.
    secret = "sk-reviewsyntheticonly0123456789abcdefghij"
    scan_id = create_job(client, valid_zip(name=secret))
    run_scan(scan_id)
    assert secret not in client.get(f"/api/v1/scans/{scan_id}/report").text
    assert secret not in client.get(f"/api/v1/scans/{scan_id}").text
    assert secret not in client.get("/api/v1/skills").text
