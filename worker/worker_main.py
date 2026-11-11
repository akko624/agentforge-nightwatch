"""Run trusted SQSP analysis jobs in a process separate from the Web API.

No uploaded skill code is imported or executed by this entry point.
"""

import logging
import signal
import time

logger = logging.getLogger("sqsp.worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","event":"%(message)s"}')
    from backend.app.core.config import get_settings
    get_settings()  # Validate local configuration before accepting work.
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


if __name__ == "__main__":
    main()
