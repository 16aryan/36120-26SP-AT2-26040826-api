"""
Unit and integration tests for Weather Intelligence FastAPI service.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app, _parse_date
from fastapi import HTTPException


@pytest.fixture
def client():
    return TestClient(app)


def test_root_endpoint(client):
    """Verify self-documenting root endpoint structure."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "Weather Intelligence API"
    assert "github" in data
    assert "endpoints" in data
    assert len(data["endpoints"]) == 5
    assert "/predict/index/comfort_climate" in data["endpoints"]
    assert "/predict/category/weather_hazard" in data["endpoints"]


def test_health_endpoint(client):
    """Verify operational health probe."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "running" in data["message"].lower()


def test_model_metadata_endpoint(client):
    """Verify metadata transparency endpoint for both models."""
    response = client.get("/model-metadata")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    
    targets = [m["target"] for m in data]
    assert "Climate Comfort Index" in targets
    assert "Weather Hazard Category" in targets
    
    cci = next(m for m in data if m["target"] == "Climate Comfort Index")
    assert cci["prediction_type"] == "regression"
    assert len(cci["features"]) > 0
    assert len(cci["feature_importance"]) > 0
    assert "performance_metrics" in cci
    
    whc = next(m for m in data if m["target"] == "Weather Hazard Category")
    assert "classification" in whc["prediction_type"]
    assert len(whc["features"]) > 0
    assert len(whc["feature_importance"]) > 0


def test_predict_comfort_climate_valid(client):
    """Verify 3-day multi-horizon CCI forecast for valid date."""
    response = client.get("/predict/index/comfort_climate?date=2025-01-01")
    assert response.status_code == 200
    data = response.json()
    assert data["input_date"] == "2025-01-01"
    assert "predictions" in data
    assert "comfort_climate" in data["predictions"]
    
    preds = data["predictions"]["comfort_climate"]
    assert len(preds) == 3
    assert "2025-01-02" in preds
    assert "2025-01-03" in preds
    assert "2025-01-04" in preds
    
    for date_key, score in preds.items():
        assert isinstance(score, (int, float))
        assert 0.0 <= score <= 100.0


def test_predict_weather_hazard_valid(client):
    """Verify +7-day multiclass hazard category prediction for valid date."""
    response = client.get("/predict/category/weather_hazard?date=2025-01-01")
    assert response.status_code == 200
    data = response.json()
    assert data["input_date"] == "2025-01-01"
    assert "predictions" in data
    assert "weather_hazard" in data["predictions"]
    
    preds = data["predictions"]["weather_hazard"]
    assert "2025-01-08" in preds
    assert preds["2025-01-08"] in ["Low Risk", "Moderate Risk", "High Risk", "Extreme Risk"]


def test_predict_date_validation_invalid_format(client):
    """Verify HTTP 422 error on malformed date string."""
    r1 = client.get("/predict/index/comfort_climate?date=not-a-date")
    assert r1.status_code == 422
    assert "Invalid date" in r1.json()["detail"]
    
    r2 = client.get("/predict/category/weather_hazard?date=2025/01/01")
    assert r2.status_code == 422
    assert "Invalid date" in r2.json()["detail"]


def test_predict_date_validation_impossible_date(client):
    """Verify HTTP 422 error on impossible calendar dates."""
    r = client.get("/predict/index/comfort_climate?date=2025-02-30")
    assert r.status_code == 422
    assert "Invalid date" in r.json()["detail"]


def test_parse_date_helper():
    """Unit test date parser internal helper directly."""
    d = _parse_date("2024-07-15")
    assert d.year == 2024
    assert d.month == 7
    assert d.day == 15
    
    with pytest.raises(HTTPException) as excinfo:
        _parse_date("bad")
    assert excinfo.value.status_code == 422
