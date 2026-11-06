import os
from datetime import timedelta

import pytest
from rq.exceptions import NoSuchJobError

from backend.app.db.models import Scan, now
from backend.app.db.session import session_factory
from backend.app.scan.queue import reconcile_redis_queue
from backend.tests.test_scans import create_job


def fake_transport(monkeypatch, status=None):
    import rq
    from rq.job import Job
    deliveries = []

    class FakeQueue:
        def __init__(self, *args, **kwargs):
            pass

        def enqueue(self, function, scan_id, **kwargs):
            deliveries.append((scan_id, kwargs["job_id"]))

    class FakeJob:
        def get_status(self):
            return status

    def fetch(*args, **kwargs):
        if status is None:
            raise NoSuchJobError("synthetic missing delivery")
        return FakeJob()

    monkeypatch.setattr(rq, "Queue", FakeQueue)
    monkeypatch.setattr(Job, "fetch", fetch)
    return deliveries


def test_redis_recovery_republishes_lost_delivery(client, monkeypatch):
    scan_id = create_job(client)
    deliveries = fake_transport(monkeypatch)
    reconcile_redis_queue(object())
    assert deliveries == [(scan_id, scan_id)]


def test_redis_recovery_preserves_existing_delivery(client, monkeypatch):
    create_job(client)
    deliveries = fake_transport(monkeypatch, "queued")
    reconcile_redis_queue(object())
    assert not deliveries


def test_redis_recovery_requeues_stale_lease(client, monkeypatch):
    scan_id = create_job(client)
    with session_factory()() as db:
        scan = db.get(Scan, scan_id)
        scan.status, scan.attempts, scan.lease_expires_at = "RUNNING", 1, now() - timedelta(seconds=1)
        db.commit()
    deliveries = fake_transport(monkeypatch)
    reconcile_redis_queue(object())
    assert deliveries == [(scan_id, f"{scan_id}-recovery-1")]


@pytest.mark.skipif(not os.getenv("SQSP_TEST_REDIS_URL"), reason="Requires isolated Redis test service (Compose test profile)")
def test_real_redis_rq_roundtrip(client):
    from redis import Redis
    from rq import Queue, Worker

    from backend.app.scan.orchestrator import run_scan
    scan_id = create_job(client)
    connection = Redis.from_url(os.environ["SQSP_TEST_REDIS_URL"])
    connection.ping()
    queue = Queue(f"sqsp-test-{scan_id}", connection=connection)
    queue.enqueue(run_scan, scan_id, job_id=scan_id, job_timeout=60)
    # Linux Worker forks a work horse; only trusted SQSP analysis code runs.
    Worker([queue], connection=connection).work(burst=True, with_scheduler=False)
    result = client.get(f"/api/v1/scans/{scan_id}").json()
    assert result["status"] == "PARTIAL"
    assert result["quality_score"] is None
