import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="kym-test-")
os.environ["KYM_DATA_DIR"] = _TMP
os.environ.pop("KYM_DATABASE_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from kym.app import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def http(client):
    return client


@pytest.fixture(autouse=True)
def isolated_state(request):
    """Each integration/security test starts with a fresh synthetic risk window and topped-up balances."""
    if "unit" in str(request.fspath):
        yield
        return
    client = request.getfixturevalue("client")
    assert client is not None
    from kym import demo

    demo.prepare_isolated_state()
    yield
