"""Scanner-independent contracts; untrusted content is data, never executable input."""
import hashlib
import re
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.redaction import redact
from backend.app.skill.parser import ParsedSkill

StageStatus = Literal["NOT_RUN", "RUNNING", "PASSED", "FINDINGS", "PARTIAL", "ERROR", "TIMEOUT", "UNAVAILABLE"]


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str
    engine: str = "builtin-static"
    category: str
    severity: Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    file_path: str
    line_start: int = Field(default=1, ge=1)
    line_end: int = Field(default=1, ge=1)
    evidence_excerpt: str = ""
    message: str
    remediation: str
    fingerprint: str = ""
    status: str = "OPEN"
    matched_rule_version: str = "1.0"
    engine_version: str = "0.1.0"
    context_note: str | None = None

    def safe(self) -> "Finding":
        evidence = redact(self.evidence_excerpt)
        path = redact(self.file_path, 512)
        canonical = re.sub(r"\s+", " ", evidence).strip().lower()
        digest = hashlib.sha256(f"{self.rule_id}\0{path}\0{canonical}".encode()).hexdigest()
        return self.model_copy(update={"file_path": path, "evidence_excerpt": evidence, "message": redact(self.message),
                                       "remediation": redact(self.remediation), "fingerprint": digest})


@dataclass(frozen=True)
class ScanContext:
    files: dict[str, bytes]
    inventory: list[dict]
    parsed: ParsedSkill


class AnalysisResult(BaseModel):
    status: StageStatus
    findings: list[Finding] = Field(default_factory=list)
    reason: str | None = None
    duration_ms: int = 0
    coverage: dict = Field(default_factory=dict)


class SkillAnalyzer(Protocol):
    name: str

    def analyze(self, context: ScanContext) -> AnalysisResult: ...


class CapabilityReport(BaseModel):
    available: bool = False
    status: str = "UNAVAILABLE"
    reason: str
    version: str = "0.1.0"


class SandboxCaseRequest(BaseModel):
    scan_id: str
    case_id: str
    profile: Literal["synthetic-filesystem", "synthetic-network"]
    artifact_sha256: str


class SandboxCaseResult(BaseModel):
    status: StageStatus
    reason: str
    events: list[dict] = Field(default_factory=list)


class SandboxRunner(Protocol):
    def capability(self) -> CapabilityReport: ...
    def run_case(self, request: SandboxCaseRequest) -> SandboxCaseResult: ...


class QualityRunner(Protocol):
    def capability(self) -> CapabilityReport: ...
    def evaluate(self, context: ScanContext, cases: list[dict]) -> AnalysisResult: ...


class SemanticAnalyzer(Protocol):
    def analyze(self, context: ScanContext) -> AnalysisResult: ...
