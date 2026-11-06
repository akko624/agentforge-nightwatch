import os

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import get_settings
from backend.app.db.models import Base
from backend.app.db.session import get_engine


@pytest.fixture
def configured(tmp_path, monkeypatch):
    test_url = os.environ.get("SQSP_TEST_DATABASE_URL")
    if test_url:
        from sqlalchemy.engine import make_url
        if make_url(test_url).database != "sqsp_test":
            raise RuntimeError("Refusing to mutate any database except explicit sqsp_test")
        monkeypatch.setenv("SQSP_DATABASE_URL", test_url)
    else:
        monkeypatch.setenv("SQSP_DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("SQSP_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("SQSP_QUEUE_BACKEND", "database")
    get_settings.cache_clear()
    get_engine.cache_clear()
    if test_url:
        Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    yield get_settings()
    if test_url:
        Base.metadata.drop_all(get_engine())
    get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
def client(configured):
    from backend.app.main import create_app
    with TestClient(create_app()) as client:
        yield client
