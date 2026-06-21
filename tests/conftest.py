import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="ai-kb-agent-tests-"))

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_ROOT / 'test.db'}"
os.environ["DOCUMENT_STORAGE_DIR"] = str(_TEST_ROOT / "documents")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DEFAULT_ADMIN_USERNAME"] = "admin"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "123456"
os.environ["DEFAULT_ADMIN_ROLE"] = "admin"
os.environ["DEFAULT_USERNAME"] = "user"
os.environ["DEFAULT_PASSWORD"] = "123456"
os.environ["DEFAULT_USER_ROLE"] = "user"

from app.db.base import Base  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def client() -> Iterator[TestClient]:
    storage_dir = _TEST_ROOT / "documents"
    shutil.rmtree(storage_dir, ignore_errors=True)
    Base.metadata.drop_all(bind=engine)
    init_db()

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_root() -> Iterator[None]:
    yield
    shutil.rmtree(_TEST_ROOT, ignore_errors=True)
