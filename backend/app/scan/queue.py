"""RQ delivery recovery. The SQL scan is authoritative; RQ is transport only."""
from sqlalchemy import or_, select, update

from backend.app.core.config import get_settings
from backend.app.db.models import AuditEvent, Scan, now
from backend.app.db.session import session_factory


def reconcile_redis_queue(connection) -> None:
    from rq import Queue
    from rq.exceptions import NoSuchJobError
    from rq.job import Job

    from backend.app.scan.orchestrator import run_scan
    settings = get_settings()
    queue = Queue("scans", connection=connection)
    with session_factory()() as db:
        scans = db.scalars(select(Scan).where(or_(Scan.status == "QUEUED", (Scan.status == "RUNNING") & (Scan.lease_expires_at < now()))).limit(100)).all()
        for scan in scans:
            if scan.attempts >= settings.max_scan_attempts:
                updated = db.execute(update(Scan).where(
                    Scan.id == scan.id, Scan.status == "RUNNING", Scan.lease_token == scan.lease_token,
                    Scan.lease_expires_at < now(), Scan.attempts >= settings.max_scan_attempts,
                ).execution_options(synchronize_session=False).values(status="FAILED", error_code="WORKER_LEASE_EXPIRED", completed_at=now(),
                         security_verdict="UNKNOWN", release_decision="INCOMPLETE", lease_token=None)).rowcount
                if updated:
                    db.add(AuditEvent(event_type="SCAN_FAILED", resource_type="scan", resource_id=scan.id,
                                      event_metadata_redacted={"error_code": "WORKER_LEASE_EXPIRED"}))
                continue
            job_id = scan.id if scan.attempts == 0 else f"{scan.id}-recovery-{scan.attempts}"
            try:
                job = Job.fetch(job_id, connection=connection)
                state = job.get_status()
                if state in {"queued", "started", "deferred", "scheduled"}:
                    continue
            except NoSuchJobError:
                pass
            queue.enqueue(run_scan, scan.id, job_id=job_id, job_timeout=settings.worker_lease_seconds,
                          result_ttl=3600, failure_ttl=86400)
        db.commit()
