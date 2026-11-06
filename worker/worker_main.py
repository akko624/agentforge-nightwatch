"""Run trusted SQSP analysis jobs in a process separate from the Web API.

No uploaded skill code is imported or executed by this entry point.
"""

import logging
import os
import signal
import time

logger = logging.getLogger("sqsp.worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","event":"%(message)s"}')
    from backend.app.core.config import get_settings
    settings = get_settings()
    backend = settings.queue_backend
    if backend == "database":
        from backend.app.scan.orchestrator import run_pending_scan

        running = True

        def stop(_signum: int, _frame: object) -> None:
            nonlocal running
            running = False

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        logger.info("database_worker_started")
        while running:
            try:
                if not run_pending_scan():
                    time.sleep(0.5)
            except Exception:
                # Do not log uploaded file contents, exception payloads or credentials.
                logger.error("database_worker_iteration_failed")
                time.sleep(1)
        return
    if backend != "redis":
        raise SystemExit("SQSP_QUEUE_BACKEND must be redis or database")

    from redis import Redis
    if os.name == "nt":
        raise SystemExit("Redis/RQ Worker requires Linux; on Windows use SQSP_QUEUE_BACKEND=database or Docker Compose")

    from rq import Worker

    connection = Redis.from_url(settings.redis_url)
    class RecoveringWorker(Worker):
        def run_maintenance_tasks(self):
            super().run_maintenance_tasks()
            from backend.app.scan.queue import reconcile_redis_queue
            try:
                reconcile_redis_queue(self.connection)
            except Exception:
                logger.error("queue_recovery_failed")

    RecoveringWorker(["scans"], connection=connection, maintenance_interval=10).work(with_scheduler=True)


if __name__ == "__main__":
    main()
