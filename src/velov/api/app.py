from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import joblib
import pandas as pd
import psycopg

app = FastAPI(
    title="Vélo'v Availability Prediction API",
    version="1.0.0",
)

MODEL_PATH = Path("models/model.joblib")
DB_URL = "postgresql://velov:velov-local-2026@localhost:5433/velov"

# Load the trained model artifact
model = None
if MODEL_PATH.exists():
    model = joblib.load(MODEL_PATH)


class PredictRequest(BaseModel):
    capacity: int
    temperature: float
    is_raining: bool
    hour: int
    day_of_week: int
    is_weekend: int
    bikes_lag_1h: float
    bikes_lag_2h: float
    bikes_rolling_3h: float


@app.get("/health")
def health_check():
    """Verify API status and PostgreSQL database connection."""
    db_status = "disconnected"
    try:
        with psycopg.connect(DB_URL, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "ok",
        "database": db_status,
        "model_loaded": model is not None,
    }


@app.post("/predict")
def predict(payload: PredictRequest):
    """Predict available bikes using the trained model artifact."""
    if model is None:
        raise HTTPException(
            status_code=500, detail="Model artifact not found. Run training first."
        )

    # Convert request payload into DataFrame feature vector
    input_data = pd.DataFrame([payload.model_dump()])

    prediction = model.predict(input_data)[0]
    return {
        "predicted_available_bikes": round(float(prediction), 2),
    }