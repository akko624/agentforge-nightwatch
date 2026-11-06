"""Persisted queue jobs and leases. Never executes Skill code."""
import hashlib
import json
import time
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, or_, select, update

from backend.app.core.config import ROOT, get_settings
from backend.app.core.errors import PlatformError
from backend.app.core.redaction import redact_object
from backend.app.db.models import AuditEvent, FindingRecord, QualityResult, Scan, Skill, SkillVersion, now
from backend.app.db.session import session_factory
from backend.app.ingest.safe_zip import read_archive
from backend.app.ingest.store import LocalArtifactStore
from backend.app.policy.decision import decide, load_policy
from backend.app.policy.permissions import permission_intersection
from backend.app.scan.adapters.disabled import DisabledSandboxRunner, NoopAnalyzer, OSVAdapter
from backend.app.scan.contracts import AnalysisResult, Finding, ScanContext
from backend.app.skill.parser import parse_skill


def _claim(scan_id: str) -> str | None:
    settings, token = get_settings(), str(uuid4())
    with session_factory()() as db:
        rowcount = db.execute(update(Scan).where(
            Scan.id == scan_id, Scan.attempts < settings.max_scan_attempts,
            or_(Scan.status == "QUEUED", (Scan.status == "RUNNING") & (Scan.lease_expires_at < now())),
        ).values(status="RUNNING", started_at=now(), attempts=Scan.attempts + 1,
                 lease_token=token, lease_expires_at=now() + timedelta(seconds=settings.worker_lease_seconds))).rowcount
        db.commit()
    return token if rowcount else None


def run_pending_scan() -> bool:
    settings = get_settings()
    with session_factory()() as db:
        expired = db.scalars(select(Scan).where(Scan.status == "RUNNING", Scan.lease_expires_at < now(), Scan.attempts >= settings.max_scan_attempts)).all()
        for row in expired:
            updated = db.execute(update(Scan).where(
                Scan.id == row.id, Scan.status == "RUNNING", Scan.lease_token == row.lease_token,
                Scan.lease_expires_at < now(), Scan.attempts >= settings.max_scan_attempts,
            ).execution_options(synchronize_session=False).values(status="FAILED", error_code="WORKER_LEASE_EXPIRED", completed_at=now(),
                     release_decision="INCOMPLETE", security_verdict="UNKNOWN", lease_token=None)).rowcount
            if updated:
                db.add(AuditEvent(event_type="SCAN_FAILED", resource_type="scan", resource_id=row.id,
                                  event_metadata_redacted={"error_code": "WORKER_LEASE_EXPIRED"}))
        db.commit()
        candidate = db.scalar(select(Scan.id).where(or_(Scan.status == "QUEUED", (Scan.status == "RUNNING") & (Scan.lease_expires_at < now()))).order_by(Scan.created_at).limit(1))
    if candidate:
        run_scan(candidate)
        return True
    return bool(expired)


def _source_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted((ROOT / "backend/app").rglob("*.py")):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def configuration_signature() -> dict:
    settings = get_settings()
    return {"ruleset_sha256": hashlib.sha256(settings.rules_path.read_bytes()).hexdigest(),
            "policy_sha256": hashlib.sha256(settings.policy_path.read_bytes()).hexdigest(),
            "scanner_source_sha256": _source_hash()}


def assert_configuration(expected: dict) -> dict:
    signature = configuration_signature()
    if any(expected.get(key) != value for key, value in signature.items()):
        raise PlatformError("SCAN_CONFIG_CHANGED", "Scanner configuration changed after enqueue; request a new scan", 409)
    return signature


def _schema_result(context: ScanContext) -> AnalysisResult:
    findings = [Finding(rule_id="SQSP-C001", engine="skill-schema", category="conformance",
                        severity="HIGH" if issue["code"] == "UNSAFE_REFERENCE" else "LOW", confidence="HIGH",
                        file_path=issue["file_path"], line_start=issue["line"], line_end=issue["line"],
                        message=issue["code"], remediation="Use an existing package-local resource reference").safe()
                for issue in context.parsed.issues]
    return AnalysisResult(status="FINDINGS" if findings else "PASSED", findings=findings,
                          coverage={"standards_version": "agentskills-2026-11", "sidecars_validated": True})


def _analyze(context: ScanContext, modes: list[str], policy: dict) -> tuple[dict, list[Finding], dict]:
    from backend.app.scan.static_rules import BuiltinStaticAnalyzer
    results = {}
    quality = {"score": None, "coverage": 0.0, "static_subscore": None, "dimensions": [],
               "reasons": ["Quality stage was not completed"]}
    required = set(policy["required_stages"]) | set(modes)
    for stage in ("schema", "static", "dependencies", "semantic", "dynamic", "quality"):
        start = time.monotonic()
        try:
            if stage == "dynamic":
                result = AnalysisResult(status="UNAVAILABLE", reason=DisabledSandboxRunner().capability().reason)
            elif stage not in required:
                result = AnalysisResult(status="NOT_RUN", reason="Not requested by scan or policy")
            elif stage == "schema":
                result = _schema_result(context)
            elif stage == "static":
                result = BuiltinStaticAnalyzer().analyze(context)
            elif stage == "dependencies":
                result = OSVAdapter().analyze(context)
            elif stage == "semantic":
                result = NoopAnalyzer().analyze(context)
            else:
                from backend.app.scan.quality import evaluate_static_quality
                quality = evaluate_static_quality(context)
                result = AnalysisResult(status="PARTIAL", reason="Only conformance and maintainability heuristics evaluated; real correctness and reliability NOT_RUN",
                                        coverage={"quality_coverage": quality["coverage"], "dimensions_completed": ["conformance", "maintainability"]})
            result.duration_ms = round((time.monotonic() - start) * 1000)
        except (TimeoutError, RecursionError):
            result = AnalysisResult(status="TIMEOUT", reason="Analyzer exceeded safe processing limits")
        except Exception:
            result = AnalysisResult(status="ERROR", reason="Analyzer failed; source and exception details are withheld")
        results[stage] = result
    stages = {name: result.model_dump(exclude={"findings"}) for name, result in results.items()}
    deduplicated = {}
    for result in results.values():
        for finding in result.findings:
            safe = finding.safe()
            deduplicated[safe.fingerprint] = safe
    return stages, list(deduplicated.values()), quality


def run_scan(scan_id: str) -> None:
    token = _claim(scan_id)
    if token is None:
        return
    settings = get_settings()
    try:
        with session_factory()() as db:
            scan = db.get(Scan, scan_id)
            signature = assert_configuration(scan.scanner_versions)
            version = db.get(SkillVersion, scan.skill_version_id)
            skill = db.get(Skill, version.skill_id)
            archive_data = LocalArtifactStore(settings.artifact_root).read(version.artifact_storage_key)
            if hashlib.sha256(archive_data).hexdigest() != version.artifact_sha256:
                raise PlatformError("ARTIFACT_INTEGRITY_ERROR", "Stored archive hash differs", 500)
            archive = read_archive(archive_data, settings)
            parsed = parse_skill(archive.files, archive.root_name)
            context = ScanContext(archive.files, archive.inventory, parsed)
            policy = load_policy(settings.policy_path)
            stages, findings, quality = _analyze(context, scan.requested_modes, policy)
            from backend.app.scan.static_rules import load_rules
            decision = decide(findings, stages, policy, scan.requested_modes)
            rule_data = load_rules()
            assert_configuration(signature)
            rule_hash = hashlib.sha256(settings.rules_path.read_bytes()).hexdigest()
            status = "PARTIAL" if any(s["status"] in {"PARTIAL", "ERROR", "TIMEOUT", "UNAVAILABLE"} for s in stages.values()) or quality["coverage"] < 1 else "COMPLETED"
            rowcount = db.execute(update(Scan).where(Scan.id == scan_id, Scan.lease_token == token, Scan.status == "RUNNING").values(
                status=status, stage_status=stages, policy_version=policy["version"],
                scanner_versions={**scan.scanner_versions, "builtin-static": rule_data.get("engine_version", "0.1.0"), "ruleset": rule_data["version"]},
                quality_score=quality["score"], quality_coverage=quality["coverage"],
                security_risk_index=decision["security_risk_index"], security_verdict=decision["security_verdict"],
                release_decision=decision["release_decision"], completed_at=now(), lease_token=None,
                lease_expires_at=None, error_code=None)).rowcount
            if not rowcount:
                db.rollback()
                return
            db.refresh(scan)
            counts = {level.lower(): sum(f.severity == level for f in findings) for level in ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")}
            report = {
                "schema_version": "1.0",
                "scan": {"id": scan.id, "status": status, "created_at": scan.created_at.isoformat(),
                         "started_at": scan.started_at.isoformat(), "completed_at": scan.completed_at.isoformat(), "requested_modes": scan.requested_modes},
                "artifact": {"name": skill.name, "sha256": version.artifact_sha256, "files": len(archive.inventory),
                             "version_id": version.id, "version_label": version.version_label,
                             "manifest": parsed.manifest, "inventory": archive.inventory},
                "engines": [{"name": name, "version": rule_data.get("engine_version", "0.1.0"), **stage} for name, stage in stages.items()],
                "compliance": {"status": stages["schema"]["status"], "issues": parsed.issues},
                "permissions": permission_intersection(parsed.security, policy),
                "security": {"verdict": decision["security_verdict"], "risk_index": decision["security_risk_index"],
                             "findings": [f.model_dump() for f in findings], "finding_counts": counts,
                             "coverage": {name: stage["status"] in {"PASSED", "FINDINGS"} for name, stage in stages.items()},
                             "limitations": ["Best-effort static rules; absence of findings is not a safety guarantee", "No Skill code, network requests or real host evaluations were executed"]},
                "quality": quality, "decision": {"status": decision["release_decision"], **decision},
                "provenance": {"policy_version": policy["version"], "ruleset_version": rule_data["version"],
                               "ruleset_sha256": rule_hash, "scanner_source_sha256": signature["scanner_source_sha256"], "policy_snapshot": policy,
                               "limits": {key: getattr(settings, key) for key in ("max_upload_bytes", "max_expanded_bytes", "max_file_bytes", "max_entries", "max_depth", "max_compression_ratio")}},
                "logs": [{"event": "stage_completed", "stage": name, "status": stage["status"], "duration_ms": stage["duration_ms"], "reason": stage["reason"]} for name, stage in stages.items()],
            }
            report = redact_object(report)
            report_bytes = json.dumps(report, ensure_ascii=False, sort_keys=True).encode()
            report_key = f"reports/{scan.id}/{hashlib.sha256(report_bytes).hexdigest()}.json"
            LocalArtifactStore(settings.artifact_root).put(report_bytes, report_key)
            scan.report_key, scan.report_json = report_key, report
            db.execute(delete(FindingRecord).where(FindingRecord.scan_id == scan_id))
            db.execute(delete(QualityResult).where(QualityResult.scan_id == scan_id))
            for finding in findings:
                db.add(FindingRecord(scan_id=scan_id, rule_id=finding.rule_id, engine=finding.engine, severity=finding.severity,
                                     fingerprint=finding.fingerprint, payload=finding.model_dump()))
            for dimension in quality["dimensions"]:
                db.add(QualityResult(scan_id=scan_id, dimension=dimension["dimension"], payload=dimension))
            db.add(AuditEvent(event_type="SCAN_COMPLETED", resource_type="scan", resource_id=scan_id,
                              event_metadata_redacted={"status": status, "ruleset_sha256": rule_hash, "decision": decision["release_decision"]}))
            db.commit()
    except Exception as exc:
        code = exc.code if isinstance(exc, PlatformError) else "SCAN_INTERNAL_ERROR"
        with session_factory()() as db:
            updated = db.execute(update(Scan).where(Scan.id == scan_id, Scan.lease_token == token).values(
                status="FAILED", error_code=code, security_verdict="UNKNOWN", release_decision="INCOMPLETE",
                completed_at=now(), lease_token=None, lease_expires_at=None)).rowcount
            if updated:
                db.add(AuditEvent(event_type="SCAN_FAILED", resource_type="scan", resource_id=scan_id,
                                  event_metadata_redacted={"error_code": code}))
            db.commit()
