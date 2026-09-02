from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_echoes_message():
    response = client.post("/chat", json={"message": "hi", "client_id": "test"})
    assert response.status_code == 200
    assert response.json() == {"message": "hi"}


def test_chat_missing_message_is_rejected():
    response = client.post("/chat", json={"client_id": "test"})
    assert response.status_code == 422


def test_chat_missing_client_id_is_rejected():
    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 422
