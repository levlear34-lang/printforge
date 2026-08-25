from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_serves_landing_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_api_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_and_job_and_result_pages_serve_html():
    for path in ("/create", "/job", "/result"):
        response = client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_classify_parametric():
    response = client.post("/api/classify", json={"text": "phone stand, 2 slots, 18 degrees"})
    assert response.status_code == 200
    assert response.json() == {"classification": "parametric"}


def test_classify_creative():
    response = client.post("/api/classify", json={"text": "Batman themed phone holder"})
    assert response.status_code == 200
    assert response.json() == {"classification": "creative"}
