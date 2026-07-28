import pytest
from fastapi.testclient import TestClient
# pyrefly: ignore [missing-import]
from src.api.main import app

@pytest.fixture(scope="module")
def client():
    return TestClient(app)