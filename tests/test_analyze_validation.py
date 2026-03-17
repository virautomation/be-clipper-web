from fastapi.testclient import TestClient

from app.main import app


def test_analyze_endpoint_invalid_youtube_url() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/jobs/analyze",
        json={
            "youtube_url": "https://example.com/video",
            "keyword": "marketing",
            "duration_target": 20,
        },
    )

    assert response.status_code == 422
