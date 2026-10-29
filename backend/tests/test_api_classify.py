from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_classify_endpoint():
    response = client.post("/api/classify", json={"text": "db connection timeout on crm-app-03"})
    assert response.status_code == 200
    data = response.json()
    assert "category" in data
    assert "severity" in data
    assert "confidence" in data
    assert "classified_by" in data
    assert "pipeline_trace" in data
    assert isinstance(data["pipeline_trace"], list)
