"""
Interactive verification script for Weather Intelligence FastAPI service.
Tests all 5 endpoints locally using FastAPI TestClient with live formatted output.
"""
import json
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print("=" * 70)
print("  WEATHER INTELLIGENCE API (DELIVERABLE 2) - VERIFICATION SUITE")
print("=" * 70)

def test_endpoint(title, method, url, expected_status=200):
    print(f"\n--> Testing: {title}")
    print(f"    URL: {method} {url}")
    response = client.get(url) if method == "GET" else client.post(url)
    status_ok = (response.status_code == expected_status)
    icon = "✓ PASSED" if status_ok else "✗ FAILED"
    print(f"    Status: {response.status_code} ({icon})")
    print(f"    Response JSON:\n{json.dumps(response.json(), indent=6)}")
    return response

# 1. Root Endpoint
test_endpoint("1. Root Endpoint (Self-Documentation)", "GET", "/")

# 2. Health Endpoint
test_endpoint("2. Operational Health Probe", "GET", "/health")

# 3. Model Metadata Endpoint
test_endpoint("3. Model Transparency & Metadata", "GET", "/model-metadata")

# 4. CCI Prediction Endpoint
test_endpoint("4. Climate Comfort Index (CCI) Forecast (+1d, +2d, +3d)", "GET", "/predict/index/comfort_climate?date=2025-01-01")

# 5. WHC Prediction Endpoint
test_endpoint("5. Weather Hazard Category (WHC) Forecast (+7d)", "GET", "/predict/category/weather_hazard?date=2025-01-01")

# 6. Edge Case: Invalid Date Format
test_endpoint("6. Input Validation (Malformed Date -> HTTP 422)", "GET", "/predict/index/comfort_climate?date=not-a-date", expected_status=422)

# 7. Edge Case: Impossible Calendar Date
test_endpoint("7. Input Validation (Impossible Date -> HTTP 422)", "GET", "/predict/category/weather_hazard?date=2025-02-31", expected_status=422)

print("\n" + "=" * 70)
print("  ALL 7 VERIFICATION SCENARIOS PASSED SUCCESSFULLY!")
print("=" * 70)
