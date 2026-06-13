from __future__ import annotations

from fastapi.testclient import TestClient

from python_claw.adapters.api.app import create_app


def test_health_endpoint_reports_skeleton_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "python-claw",
        "status": "ok",
        "stage": "skeleton",
    }
