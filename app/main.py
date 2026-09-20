"""
Weather Intelligence API
FastAPI application serving Climate Comfort Index (CCI) regression and
Weather Hazard Category (WHC) classification predictions for Sydney, NSW, Australia.

UTS 36120 - Advanced Machine Learning Applications (AT2)
Student: Aryan Goel (26040826)
"""
from datetime import date, datetime, timedelta
import json
import logging
from pathlib import Path
import pickle
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("weather-intel-api")

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"

GITHUB_URL = "https://github.com/16aryan/36120-26SP-AT2-26040826-api"

app = FastAPI(
    title="Weather Intelligence API",
    description="Production machine learning services for forecasting Climate Comfort Index (CCI) and Weather Hazard Category (WHC).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory storage for models and feature store
CCI_ARTIFACT: Optional[Dict[str, Any]] = None
WHC_ARTIFACT: Optional[Dict[str, Any]] = None
CCI_METADATA: Optional[Dict[str, Any]] = None
WHC_METADATA: Optional[Dict[str, Any]] = None
FEATURE_STORE: Optional[pd.DataFrame] = None


def load_artifacts():
    global CCI_ARTIFACT, WHC_ARTIFACT, CCI_METADATA, WHC_METADATA, FEATURE_STORE
    
    # 1. Load CCI Model & Metadata
    cci_pkl = MODELS_DIR / "comfort_climate" / "cci_model.pkl"
    cci_json = MODELS_DIR / "comfort_climate" / "metadata.json"
    if cci_pkl.exists():
        with open(cci_pkl, "rb") as f:
            CCI_ARTIFACT = pickle.load(f)
        logger.info("Loaded CCI model (%s)", CCI_ARTIFACT.get("algorithm"))
    if cci_json.exists():
        with open(cci_json, "r") as f:
            CCI_METADATA = json.load(f)
            
    # 2. Load WHC Model & Metadata
    whc_pkl = MODELS_DIR / "weather_hazard" / "whc_model.pkl"
    whc_json = MODELS_DIR / "weather_hazard" / "metadata.json"
    if whc_pkl.exists():
        with open(whc_pkl, "rb") as f:
            WHC_ARTIFACT = pickle.load(f)
        logger.info("Loaded WHC model (%s)", WHC_ARTIFACT.get("algorithm"))
    if whc_json.exists():
        with open(whc_json, "r") as f:
            WHC_METADATA = json.load(f)

    # 3. Load Precomputed Feature Store
    feature_csv = DATA_DIR / "sydney_daily_features.csv"
    if feature_csv.exists():
        FEATURE_STORE = pd.read_csv(feature_csv)
        FEATURE_STORE["date"] = FEATURE_STORE["date"].astype(str)
        FEATURE_STORE = FEATURE_STORE.set_index("date")
        logger.info("Loaded feature store with %d daily records", len(FEATURE_STORE))


# Load on startup
load_artifacts()


def _parse_date(date_str: str) -> date:
    """Parse and validate ISO date string YYYY-MM-DD strictly."""
    if not isinstance(date_str, str) or len(date_str) != 10:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date '{date_str}'. Expected format YYYY-MM-DD.",
        )
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
        return parsed
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date '{date_str}'. Expected format YYYY-MM-DD.",
        )


def _get_feature_vector(target_date: date, feature_list: List[str]) -> pd.DataFrame:
    """Extract feature row for target date from store, or fallback to climatology."""
    date_str = target_date.strftime("%Y-%m-%d")
    
    if FEATURE_STORE is not None and date_str in FEATURE_STORE.index:
        row = FEATURE_STORE.loc[[date_str]]
        # Fill any missing requested features
        for f in feature_list:
            if f not in row.columns:
                row[f] = 0.0
        return row[feature_list]
        
    # Dynamic generation or Climatological fallback for unseen dates
    doy = target_date.timetuple().tm_yday
    month = target_date.month
    
    # Use closest available day of year across historical store as representative atmospheric base
    if FEATURE_STORE is not None and len(FEATURE_STORE) > 0:
        # Match same month and day across available years (e.g. 2024)
        sample_dates = [d for d in FEATURE_STORE.index if d.endswith(f"-{month:02d}-{target_date.day:02d}")]
        if not sample_dates:
            sample_dates = [d for d in FEATURE_STORE.index if f"-{month:02d}-" in d]
        fallback_idx = sample_dates[-1] if sample_dates else FEATURE_STORE.index[-1]
        row = FEATURE_STORE.loc[[fallback_idx]].copy()
    else:
        row = pd.DataFrame([{f: 0.0 for f in feature_list}])

    # Update calendar cyclical terms for the actual requested date
    if "sin_dayofyear" in feature_list:
        row["sin_dayofyear"] = np.sin(2 * np.pi * doy / 365.25)
    if "cos_dayofyear" in feature_list:
        row["cos_dayofyear"] = np.cos(2 * np.pi * doy / 365.25)
    if "sin_month" in feature_list:
        row["sin_month"] = np.sin(2 * np.pi * month / 12.0)
    if "cos_month" in feature_list:
        row["cos_month"] = np.cos(2 * np.pi * month / 12.0)

    for f in feature_list:
        if f not in row.columns:
            row[f] = 0.0
            
    return row[feature_list]


@app.get("/")
def root():
    """Self-documenting root endpoint matching UTS AT2 specification."""
    return {
        "project": "Weather Intelligence API",
        "description": "Machine learning services for weather forecasting",
        "version": "1.0.0",
        "github": GITHUB_URL,
        "endpoints": [
            "/",
            "/health",
            "/predict/index/comfort_climate",
            "/predict/category/weather_hazard",
            "/model-metadata",
        ],
    }


@app.get("/health")
def health():
    """Operational health check probe."""
    is_healthy = (CCI_ARTIFACT is not None) and (WHC_ARTIFACT is not None)
    return {
        "status": "healthy" if is_healthy else "degraded",
        "message": "Weather Intelligence API is running",
    }


@app.get("/model-metadata")
def model_metadata():
    """Return comprehensive metadata for both deployed models."""
    metadata_list = []
    
    # 1. CCI Metadata
    if CCI_METADATA:
        metadata_list.append({
            "target": CCI_METADATA.get("target", "Climate Comfort Index"),
            "prediction_type": CCI_METADATA.get("prediction_type", "regression"),
            "algorithm": CCI_METADATA.get("algorithm", "Ridge Regressor"),
            "forecast_horizon": CCI_METADATA.get("forecast_horizon", "3 Days"),
            "features": CCI_METADATA.get("features", []),
            "feature_importance": CCI_METADATA.get("feature_importance", {}),
            "performance_metrics": CCI_METADATA.get("performance_metrics", {}),
        })
    else:
        metadata_list.append({
            "target": "Climate Comfort Index",
            "prediction_type": "regression",
            "algorithm": "Ridge",
            "forecast_horizon": "3 Days",
            "features": [],
            "feature_importance": {},
            "performance_metrics": {},
        })

    # 2. WHC Metadata
    if WHC_METADATA:
        metadata_list.append({
            "target": WHC_METADATA.get("target", "Weather Hazard Category"),
            "prediction_type": WHC_METADATA.get("prediction_type", "multiclass classification"),
            "algorithm": WHC_METADATA.get("algorithm", "Random Forest"),
            "forecast_horizon": WHC_METADATA.get("forecast_horizon", "7 Days"),
            "features": WHC_METADATA.get("features", []),
            "feature_importance": WHC_METADATA.get("feature_importance", {}),
            "performance_metrics": WHC_METADATA.get("performance_metrics", {}),
        })
    else:
        metadata_list.append({
            "target": "Weather Hazard Category",
            "prediction_type": "multiclass classification",
            "algorithm": "Random Forest",
            "forecast_horizon": "7 Days",
            "features": [],
            "feature_importance": {},
            "performance_metrics": {},
        })
        
    return metadata_list


@app.get("/predict/index/comfort_climate")
def predict_comfort_climate(date: str = Query(..., description="Forecast starting date in format YYYY-MM-DD")):
    """Forecast Climate Comfort Index (CCI) for the next three days (+1, +2, +3 days)."""
    input_date = _parse_date(date)
    
    if CCI_ARTIFACT is None:
        raise HTTPException(status_code=503, detail="Climate Comfort Index model is not loaded.")
        
    features_list = CCI_ARTIFACT["features_list"]
    model = CCI_ARTIFACT["model"]
    scaler = CCI_ARTIFACT.get("scaler")
    
    # Extract feature row
    X_df = _get_feature_vector(input_date, features_list)
    
    # Scale if scaler present
    if scaler is not None:
        X_scaled = scaler.transform(X_df)
        X_in = pd.DataFrame(X_scaled, columns=features_list)
    else:
        X_in = X_df
        
    raw_preds = model.predict(X_in)[0]
    
    predictions = {}
    for i in range(1, 4):
        target_day = input_date + timedelta(days=i)
        pred_val = float(raw_preds[i - 1])
        # Clip strictly to valid CCI range [0.0, 100.0] and round to 1 decimal
        bounded_score = round(max(0.0, min(100.0, pred_val)), 1)
        predictions[target_day.strftime("%Y-%m-%d")] = bounded_score

    return {
        "input_date": input_date.strftime("%Y-%m-%d"),
        "predictions": {"comfort_climate": predictions},
    }


@app.get("/predict/category/weather_hazard")
def predict_weather_hazard(date: str = Query(..., description="Forecast starting date in format YYYY-MM-DD")):
    """Predict Weather Hazard Category (WHC) exactly seven days after the supplied date."""
    input_date = _parse_date(date)
    target_day = input_date + timedelta(days=7)
    
    if WHC_ARTIFACT is None:
        raise HTTPException(status_code=503, detail="Weather Hazard Category model is not loaded.")
        
    features_list = WHC_ARTIFACT["features_list"]
    model = WHC_ARTIFACT["model"]
    scaler = WHC_ARTIFACT.get("scaler")
    labels = WHC_ARTIFACT.get("class_labels", {0: "Low Risk", 1: "Moderate Risk", 2: "High Risk", 3: "Extreme Risk"})
    
    # Extract feature row
    X_df = _get_feature_vector(input_date, features_list)
    
    if scaler is not None:
        X_scaled = scaler.transform(X_df)
        X_in = pd.DataFrame(X_scaled, columns=features_list)
    else:
        X_in = X_df
        
    raw_pred = model.predict(X_in)[0]
    class_int = int(raw_pred)
    risk_label = labels.get(class_int, labels.get(str(class_int), f"Class {class_int}"))
    
    return {
        "input_date": input_date.strftime("%Y-%m-%d"),
        "predictions": {
            "weather_hazard": {
                target_day.strftime("%Y-%m-%d"): risk_label
            }
        },
    }
