from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.scan.contracts import Finding


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class UploadResult(BaseModel):
    skill_id: str
    version_id: str
    sha256: str


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: str
    modes: list[str] = Field(default_factory=lambda: ["schema", "static", "quality"], max_length=8)
    force: bool = False


class ScanCreated(BaseModel):
    scan_id: str
    status: str


class StageResult(BaseModel):
    status: str
    reason: str | None = None
    duration_ms: int = 0
    coverage: dict = Field(default_factory=dict)


class ScanSummary(BaseModel):
    scan_id: str
    skill_id: str
    version_id: str
    skill_name: str
    version_label: str | None
    artifact_sha256: str
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "PARTIAL", "FAILED"]
    stages: dict[str, StageResult]
    quality_score: float | None
    quality_coverage: float
    static_quality_subscore: float | None
    security_risk_index: float | None
    security_verdict: str
    release_decision: str
    finding_counts: dict[str, int]
    policy_version: str
    scanner_versions: dict
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    attempts: int


class ScanList(BaseModel):
    items: list[ScanSummary]
    total: int


class FindingList(BaseModel):
    items: list[Finding]
    total: int


class QualityReport(BaseModel):
    score: float | None
    coverage: float
    static_subscore: float | None
    dimensions: list[dict]
    reasons: list[str]


class FullReport(BaseModel):
    schema_version: str
    scan: dict
    artifact: dict
    engines: list[dict]
    compliance: dict
    permissions: dict
    security: dict
    quality: QualityReport
    decision: dict
    provenance: dict
    logs: list[dict]


class ScanDiff(BaseModel):
    left: ScanSummary
    right: ScanSummary
    new_findings: list[Finding]
    resolved_findings: list[Finding]
    unchanged_findings: list[Finding]
    changed_evidence: list[dict]
    quality_changes: list[dict]
    coverage_changes: dict
    policy_changed: bool
    ruleset_changed: bool
    scanner_changed: bool
    comparability: dict
    warnings: list[str]
