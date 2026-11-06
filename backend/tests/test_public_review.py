import pytest

from backend.tests.test_public_report import private_report
from scripts.build_report_site import public_summary


def test_public_snapshot_rejects_static_score_without_measured_static_dimensions():
    report = private_report()
    quality = report["quality"]
    quality["coverage"] = 0
    quality["static_subscore"] = 99
    for dimension in quality["dimensions"]:
        dimension["status"], dimension["score"] = "NOT_RUN", None
    with pytest.raises(ValueError):
        public_summary(report)
