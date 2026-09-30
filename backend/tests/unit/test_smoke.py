from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from footsim.api import routes
from footsim.api.app import app, create_app
from footsim.api.session import CareerSession


def test_health() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_says_whether_saves_are_the_default(tmp_path: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    # The browser tests refuse a server whose saves are the default folder (the user's careers).
    # Nothing here touches the real folder: the default is pointed at a temporary one.
    real = tmp_path / "real"
    monkeypatch.setattr(routes, "DEFAULT_SAVES", real)
    for root, expected in ((real, True), (tmp_path / "throwaway", False)):
        client = TestClient(create_app(CareerSession(root, tmp_path / "world.sqlite"),
                                       frontend=None))
        body = client.get("/api/health").json()
        assert body["default_saves"] is expected
        assert body["saves_dir"] == str(root.resolve())
