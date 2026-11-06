from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


JsonType = JSON().with_variant(JSONB(), "postgresql")


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("name", "owner_label"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_label: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("skill_id", "artifact_sha256"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), index=True)
    version_label: Mapped[str | None] = mapped_column(String(64))
    artifact_sha256: Mapped[str] = mapped_column(String(64), index=True)
    artifact_storage_key: Mapped[str] = mapped_column(String(255))
    manifest_json: Mapped[dict] = mapped_column(JsonType)
    file_inventory_json: Mapped[list] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class Scan(Base):
    __tablename__ = "scans"
    __table_args__ = (Index("ix_scan_queue", "status", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    skill_version_id: Mapped[str] = mapped_column(ForeignKey("skill_versions.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    requested_modes: Mapped[list] = mapped_column(JsonType, default=list)
    stage_status: Mapped[dict] = mapped_column(JsonType, default=dict)
    scanner_versions: Mapped[dict] = mapped_column(JsonType, default=dict)
    policy_version: Mapped[str] = mapped_column(String(50), default="1.0")
    quality_score: Mapped[float | None] = mapped_column(Float)
    quality_coverage: Mapped[float] = mapped_column(Float, default=0)
    security_risk_index: Mapped[float | None] = mapped_column(Float)
    security_verdict: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    release_decision: Mapped[str] = mapped_column(String(20), default="INCOMPLETE")
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    report_key: Mapped[str | None] = mapped_column(String(255))
    report_json: Mapped[dict | None] = mapped_column(JsonType)


class FindingRecord(Base):
    __tablename__ = "findings"
    __table_args__ = (UniqueConstraint("scan_id", "fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(80), index=True)
    engine: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(20), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JsonType)


class QualityResult(Base):
    __tablename__ = "quality_results"
    __table_args__ = (UniqueConstraint("scan_id", "dimension"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    dimension: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JsonType)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    event_type: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    event_metadata_redacted: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
