from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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
