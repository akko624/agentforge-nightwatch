from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.errors import PlatformError
from backend.app.core.redaction import redact, redact_object
from backend.app.db.models import AuditEvent, FindingRecord, Scan, Skill, SkillVersion, now
from backend.app.db.session import get_db
from backend.app.ingest.safe_zip import read_archive
from backend.app.ingest.store import LocalArtifactStore
from backend.app.schemas.api import (
    ErrorEnvelope,
    FindingList,
    FullReport,
    QualityReport,
    ScanCreated,
    ScanDiff,
    ScanList,
    ScanRequest,
    ScanSummary,
    UploadResult,
)
from backend.app.skill.parser import parse_skill

router = APIRouter(prefix="/api/v1", responses={
    status: {"model": ErrorEnvelope, "description": "Unified SQSP error"}
    for status in (400, 404, 409, 413, 422, 500, 503)
})
DB = Annotated[Session, Depends(get_db)]


@router.post("/skills/upload", response_model=UploadResult, status_code=201)
async def upload_skill(db: DB, file: UploadFile = File(...), owner_label: str = Form(default="", max_length=100)):
    settings = get_settings()
    data = bytearray()
    try:
        while chunk := await file.read(65536):
            data.extend(chunk)
            if len(data) > settings.max_upload_bytes:
                raise PlatformError("ARCHIVE_LIMIT", "Upload exceeds size limit", 413)
    finally:
        await file.close()
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise PlatformError("INVALID_ARCHIVE", "Only ZIP uploads are supported")
    archive = read_archive(bytes(data), settings)
    parsed = parse_skill(archive.files, archive.root_name)
    key = f"archives/{archive.sha256[:2]}/{archive.sha256}.zip"
    LocalArtifactStore(settings.artifact_root).put(bytes(data), key)
    owner = redact(owner_label, 100)
    # The unique constraints are authoritative under concurrent uploads.
    for attempt in range(3):
        try:
            skill = db.scalar(select(Skill).where(Skill.name == parsed.name, Skill.owner_label == owner))
            if skill is None:
                skill = Skill(name=parsed.name, owner_label=owner)
                db.add(skill)
                db.flush()
            version = db.scalar(select(SkillVersion).where(SkillVersion.skill_id == skill.id, SkillVersion.artifact_sha256 == archive.sha256))
            if version is None:
                version = SkillVersion(skill_id=skill.id, version_label=parsed.manifest["metadata"].get("version"),
                                       artifact_sha256=archive.sha256, artifact_storage_key=key,
                                       manifest_json=parsed.manifest, file_inventory_json=redact_object(archive.inventory))
                db.add(version)
                db.flush()
                db.add(AuditEvent(event_type="ARTIFACT_IMPORTED", resource_type="skill_version", resource_id=version.id,
                                  event_metadata_redacted={"sha256": archive.sha256}))
            db.commit()
            return UploadResult(skill_id=skill.id, version_id=version.id, sha256=archive.sha256)
        except IntegrityError:
            db.rollback()
            if attempt == 2:
                raise PlatformError("UPLOAD_CONFLICT", "Concurrent import; retry request", 409) from None


@router.get("/skills")
def list_skills(db: DB, q: str = Query(default="", max_length=100), limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    query = select(Skill)
    if q:
        query = query.where(Skill.name.contains(q, autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Skill.created_at.desc()).offset(offset).limit(limit)).all()
    return {"items": [{"id": row.id, "name": redact(row.name, 64), "owner_label": row.owner_label, "created_at": row.created_at} for row in rows], "total": total}


@router.get("/skills/{skill_id}/versions")
def list_versions(skill_id: str, db: DB):
    if db.get(Skill, skill_id) is None:
        raise PlatformError("NOT_FOUND", "Skill not found", 404)
    rows = db.scalars(select(SkillVersion).where(SkillVersion.skill_id == skill_id).order_by(SkillVersion.created_at.desc())).all()
    return {"items": [{"id": row.id, "version_label": row.version_label, "sha256": row.artifact_sha256,
                       "manifest": row.manifest_json, "file_inventory": row.file_inventory_json, "created_at": row.created_at} for row in rows]}


def get_scan(db: Session, scan_id: str) -> Scan:
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise PlatformError("NOT_FOUND", "Scan not found", 404)
    return scan


def summary(db: Session, scan: Scan) -> ScanSummary:
    version = db.get(SkillVersion, scan.skill_version_id)
    skill = db.get(Skill, version.skill_id)
    report = scan.report_json or {}
    return ScanSummary(scan_id=scan.id, skill_id=skill.id, version_id=version.id, skill_name=redact(skill.name, 64),
                       version_label=version.version_label, artifact_sha256=version.artifact_sha256,
                       status=scan.status, stages=scan.stage_status, quality_score=scan.quality_score,
                       quality_coverage=scan.quality_coverage, static_quality_subscore=report.get("quality", {}).get("static_subscore"),
                       security_risk_index=scan.security_risk_index, security_verdict=scan.security_verdict,
                       release_decision=scan.release_decision, finding_counts=report.get("security", {}).get("finding_counts", {}),
                       policy_version=scan.policy_version, scanner_versions=scan.scanner_versions,
                       created_at=scan.created_at, started_at=scan.started_at, completed_at=scan.completed_at,
                       error_code=scan.error_code, attempts=scan.attempts)


@router.post("/scans", response_model=ScanCreated, status_code=202)
def create_scan(body: ScanRequest, db: DB):
    from backend.app.policy.decision import STAGES, load_policy
    settings = get_settings()
    modes = sorted(set(body.modes))
    if not modes or not set(modes) <= STAGES:
        raise PlatformError("INVALID_MODES", "Unsupported or empty scan modes", 422)
    if db.get(SkillVersion, body.version_id) is None:
        raise PlatformError("NOT_FOUND", "Skill version not found", 404)
    policy = load_policy(settings.policy_path)
    from backend.app.scan.orchestrator import configuration_signature
    signature = configuration_signature()
    if not body.force:
        candidates = db.scalars(select(Scan).where(Scan.skill_version_id == body.version_id).order_by(Scan.created_at.desc()).limit(100)).all()
        for candidate in candidates:
            if candidate.requested_modes == modes and all(candidate.scanner_versions.get(k) == v for k, v in signature.items()) and candidate.status != "FAILED":
                return ScanCreated(scan_id=candidate.id, status=candidate.status)
    scan = Scan(skill_version_id=body.version_id, requested_modes=modes, policy_version=policy["version"], scanner_versions=signature,
                stage_status={name: {"status": "NOT_RUN", "reason": "Queued"} for name in sorted(STAGES)})
    db.add(scan)
    db.flush()
    db.add(AuditEvent(event_type="SCAN_QUEUED", resource_type="scan", resource_id=scan.id,
                      event_metadata_redacted={"modes": modes}))
    db.commit()
    if settings.queue_backend == "redis":
        try:
            from redis import Redis
            from rq import Queue

            from backend.app.scan.orchestrator import run_scan
            Queue("scans", connection=Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)).enqueue(
                run_scan, scan.id, job_timeout=settings.worker_lease_seconds, result_ttl=3600, failure_ttl=86400,
                job_id=scan.id)
        except Exception:
            updated = db.execute(update(Scan).where(Scan.id == scan.id, Scan.status == "QUEUED").execution_options(synchronize_session=False).values(
                status="FAILED", error_code="QUEUE_UNAVAILABLE", completed_at=now())).rowcount
            if updated:
                db.add(AuditEvent(event_type="SCAN_FAILED", resource_type="scan", resource_id=scan.id,
                                  event_metadata_redacted={"error_code": "QUEUE_UNAVAILABLE"}))
            db.commit()
            db.refresh(scan)
            if not updated:
                # An ACK may be lost after Redis accepted the job. Never replace
                # a concurrent worker's RUNNING/completed state with a queue error.
                return ScanCreated(scan_id=scan.id, status=scan.status)
            raise PlatformError("QUEUE_UNAVAILABLE", "Scan could not be queued", 503, {"scan_id": scan.id}) from None
    return ScanCreated(scan_id=scan.id, status=scan.status)


@router.get("/scans", response_model=ScanList)
def list_scans(db: DB, q: str = Query(default="", max_length=100), status: Literal["QUEUED", "RUNNING", "COMPLETED", "PARTIAL", "FAILED"] | None = None,
               limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    query = select(Scan).join(SkillVersion).join(Skill)
    if q:
        query = query.where(Skill.name.contains(q, autoescape=True))
    if status:
        query = query.where(Scan.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    scans = db.scalars(query.order_by(Scan.created_at.desc()).offset(offset).limit(limit)).all()
    return ScanList(items=[summary(db, scan) for scan in scans], total=total)


@router.get("/scans/{scan_id}", response_model=ScanSummary)
def scan_summary(scan_id: str, db: DB):
    return summary(db, get_scan(db, scan_id))


@router.get("/scans/{scan_id}/findings", response_model=FindingList)
def scan_findings(scan_id: str, db: DB, severity: Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None,
                  engine: str | None = Query(default=None, max_length=80), limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    get_scan(db, scan_id)
    query = select(FindingRecord).where(FindingRecord.scan_id == scan_id)
    if severity:
        query = query.where(FindingRecord.severity == severity)
    if engine:
        query = query.where(FindingRecord.engine == engine)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(FindingRecord.rule_id, FindingRecord.fingerprint).offset(offset).limit(limit)).all()
    return FindingList(items=[row.payload for row in rows], total=total)


def completed_report(scan: Scan) -> dict:
    if scan.report_json is None:
        raise PlatformError("REPORT_NOT_READY", "Report is unavailable until analysis completes", 409,
                            {"status": scan.status, "error_code": scan.error_code})
    return scan.report_json


@router.get("/scans/{scan_id}/quality", response_model=QualityReport)
def scan_quality(scan_id: str, db: DB):
    return completed_report(get_scan(db, scan_id))["quality"]


@router.get("/scans/{scan_id}/report", response_model=FullReport)
def scan_report(scan_id: str, db: DB, response: Response, format: Literal["json"] = "json"):
    report = completed_report(get_scan(db, scan_id))
    response.headers["Content-Disposition"] = f'attachment; filename="sqsp-{get_scan(db, scan_id).id}.json"'
    return report


@router.get("/rules")
def rules(category: str | None = Query(default=None, max_length=80)):
    from backend.app.scan.static_rules import load_rules
    data = load_rules()
    return {**data, "rules": [rule for rule in data["rules"] if category is None or rule["category"] == category]}


@router.get("/compare", response_model=ScanDiff)
def compare(left: str, right: str, db: DB):
    from backend.app.reports.compare import compare_reports
    left_scan, right_scan = get_scan(db, left), get_scan(db, right)
    left_version = db.get(SkillVersion, left_scan.skill_version_id)
    right_version = db.get(SkillVersion, right_scan.skill_version_id)
    if left_version.skill_id != right_version.skill_id:
        raise PlatformError("UNRELATED_SCANS", "Only versions of the same Skill can be compared", 409)
    difference = compare_reports(completed_report(left_scan), completed_report(right_scan))
    return ScanDiff(left=summary(db, left_scan), right=summary(db, right_scan), **difference)
