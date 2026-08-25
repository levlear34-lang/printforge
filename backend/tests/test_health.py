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


def test_unknown_page_route_serves_custom_404_html():
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "404" in response.text


def test_unknown_api_route_stays_json():
    response = client.get("/api/this-does-not-exist")
    assert response.status_code == 404
    assert "application/json" in response.headers["content-type"]


def test_robots_txt_served():
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "User-agent" in response.text


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
