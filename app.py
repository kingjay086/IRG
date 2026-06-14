import os
import asyncio
import threading
import subprocess
import sys
import logging
from typing import Set
import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from train import train_model

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IRG_Server")

# Paths
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(WORKSPACE_DIR, "governor_model.pkl")
CSV_PATH = os.path.join(WORKSPACE_DIR, "server_logs.csv")

app = FastAPI(title="Intelligent Resource Governor API")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Simulation & Middleware State
class ServerState:
    def __init__(self):
        self.ai_middleware_active = False
        self.simulate_load_spike = False
        
        # Telemetry metrics
        self.cpu_utilization = 20.0
        self.ram_utilization = 40.0
        self.request_rate = 10.0
        self.context_switches = 500.0
        self.worker_threads = 8
        self.latency_ms = 10.0
        self.governor_status = "STABLE"  # STABLE or GOVERNED
        
        # Statistics counters
        self.allowed_browse = 0
        self.shed_browse = 0
        self.allowed_pay = 0
        
        # Subprocess state
        self.locust_process = None
        
        # ML Model holder
        self.model = None
        self.load_model()
        
    def start_locust(self):
        if self.locust_process is None:
            logger.info("Starting Locust traffic simulator...")
            cmd = [sys.executable, "-m", "locust", "-f", "locustfile.py", "--headless", "-u", "100", "-r", "10", "--host", "http://127.0.0.1:8088"]
            # Start locust in the background, ignoring stdout/stderr to avoid cluttering terminal
            self.locust_process = subprocess.Popen(cmd, cwd=WORKSPACE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop_locust(self):
        if self.locust_process is not None:
            logger.info("Stopping Locust traffic simulator...")
            self.locust_process.terminate()
            self.locust_process.wait()
            self.locust_process = None

    def load_model(self):
        if os.path.exists(MODEL_PATH):
            try:
                self.model = joblib.load(MODEL_PATH)
                logger.info("Successfully loaded ML model from disk.")
            except Exception as e:
                logger.error(f"Error loading ML model: {e}")
                self.model = None
        else:
            logger.warning("No ML model found. Operating in rule-based fallback mode.")
            self.model = None

    def predict_risk(self) -> int:
        """
        Uses the Random Forest model to predict risk (1=Instability, 0=Stable)
        based on current real-time telemetry metrics.
        Fails back to rule-based logic if the model is not loaded.
        """
        if self.model is not None:
            try:
                # Features: ['cpu_utilization', 'ram_utilization', 'request_rate', 'context_switches', 'worker_threads']
                features = np.array([[
                    self.cpu_utilization,
                    self.ram_utilization,
                    self.request_rate,
                    self.context_switches,
                    self.worker_threads
                ]])
                prediction = self.model.predict(features)[0]
                return int(prediction)
            except Exception as e:
                logger.error(f"Inference error: {e}")
                
        # Rule-based fallback (CPU > 80% or RAM > 80%)
        if self.cpu_utilization > 80.0 or self.ram_utilization > 80.0:
            return 1
        return 0

state = ServerState()
active_websockets: Set[WebSocket] = set()

# WebSocket Broadcaster Task
async def telemetry_broadcaster():
    """
    Simulates real-time system resource changes every second, runs inference
    if middleware is active, handles load-shedding feedback loops, and broadcasts
    metrics via WebSockets to connected dashboards.
    """
    t = 0
    while True:
        try:
            # 1. Resource Simulation Logic
            if state.simulate_load_spike:
                t += 1
                # Normal spike behavior
                if state.ai_middleware_active and state.governor_status == "GOVERNED":
                    # Load shedding is active: system is protected and metrics recover
                    state.cpu_utilization = max(state.cpu_utilization - 5.0, 45.0) + np.random.uniform(-2, 2)
                    state.ram_utilization = min(state.ram_utilization + 0.1, 75.0) # Leak slows down
                    state.request_rate = min(state.request_rate + 5.0, 220.0) + np.random.uniform(-5, 5)
                    state.worker_threads = max(state.worker_threads - 1, 12)
                    state.context_switches = state.cpu_utilization * 30 + np.random.uniform(500, 1000)
                    state.latency_ms = max(state.latency_ms - 100, 35.0) + np.random.uniform(-5, 5)
                else:
                    # No load shedding active: system enters Reload Death Spiral
                    state.cpu_utilization = min(state.cpu_utilization + 8.0, 99.8)
                    state.ram_utilization = min(state.ram_utilization + 1.2, 95.0) # Quick RAM leak
                    state.request_rate = min(state.request_rate + 25.0, 300.0) + np.random.uniform(-10, 10)
                    state.worker_threads = min(state.worker_threads + 2, 45)
                    state.context_switches = min(state.context_switches + 800, 7500.0)
                    # Exponential latency spike
                    state.latency_ms = min(state.latency_ms * 1.5 + 50, 2500.0)
            else:
                # Idle state
                t = 0
                state.cpu_utilization = max(state.cpu_utilization - 4.0, np.random.uniform(15, 25))
                state.ram_utilization = max(state.ram_utilization - 0.5, np.random.uniform(35, 42))
                state.request_rate = max(state.request_rate - 10.0, np.random.uniform(5, 12))
                state.worker_threads = max(state.worker_threads - 1, np.random.randint(6, 9))
                state.context_switches = state.cpu_utilization * 25 + np.random.uniform(200, 400)
                state.latency_ms = max(state.latency_ms - 200.0, np.random.uniform(5, 12))

            # Bounds capping
            state.cpu_utilization = round(max(0.0, min(100.0, state.cpu_utilization)), 1)
            state.ram_utilization = round(max(0.0, min(100.0, state.ram_utilization)), 1)
            state.request_rate = round(max(0.0, state.request_rate), 1)
            state.context_switches = round(max(0.0, state.context_switches), 1)
            state.latency_ms = round(state.latency_ms, 1)

            # 2. Risk Inference
            if state.ai_middleware_active:
                prediction = state.predict_risk()
                state.governor_status = "GOVERNED" if prediction == 1 else "STABLE"
            else:
                state.governor_status = "STABLE"

            # 3. WebSocket Broadcast
            payload = {
                "ai_middleware_active": state.ai_middleware_active,
                "simulate_load_spike": state.simulate_load_spike,
                "cpu_utilization": state.cpu_utilization,
                "ram_utilization": state.ram_utilization,
                "request_rate": state.request_rate,
                "context_switches": state.context_switches,
                "worker_threads": state.worker_threads,
                "latency_ms": state.latency_ms,
                "governor_status": state.governor_status,
                "allowed_browse": state.allowed_browse,
                "shed_browse": state.shed_browse,
                "allowed_pay": state.allowed_pay
            }

            if active_websockets:
                # Construct clean JSON
                await asyncio.gather(*[ws.send_json(payload) for ws in active_websockets], return_exceptions=True)

        except Exception as e:
            logger.error(f"Broadcaster simulation error: {e}")
        
        await asyncio.sleep(1.0)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(telemetry_broadcaster())
    logger.info("Telemetry simulator background loop initialized.")

# REST Routes
@app.get("/api/state")
def get_state():
    return {
        "ai_middleware_active": state.ai_middleware_active,
        "simulate_load_spike": state.simulate_load_spike,
        "governor_status": state.governor_status,
        "allowed_browse": state.allowed_browse,
        "shed_browse": state.shed_browse,
        "allowed_pay": state.allowed_pay,
        "has_model": state.model is not None
    }

class ToggleRequest(BaseModel):
    value: bool

@app.post("/api/toggle-middleware")
def toggle_middleware(req: ToggleRequest):
    state.ai_middleware_active = req.value
    logger.info(f"AI Middleware active toggled to: {state.ai_middleware_active}")
    return {"status": "success", "ai_middleware_active": state.ai_middleware_active}

@app.post("/api/toggle-spike")
def toggle_spike(req: ToggleRequest):
    state.simulate_load_spike = req.value
    # Reset counters when starting/stopping spikes
    state.allowed_browse = 0
    state.shed_browse = 0
    state.allowed_pay = 0
    
    # Start or stop the actual Locust HTTP traffic based on the toggle
    if state.simulate_load_spike:
        state.start_locust()
    else:
        state.stop_locust()
        
    logger.info(f"Simulate Load Spike toggled to: {state.simulate_load_spike}")
    return {"status": "success", "simulate_load_spike": state.simulate_load_spike}

@app.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    try:
        content = await file.read()
        # Ensure workspace exists
        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        # Write to server_logs.csv
        with open(CSV_PATH, "wb") as f:
            f.write(content)
        
        # Quick validation
        df = pd.read_csv(CSV_PATH)
        required_cols = ['cpu_utilization', 'ram_utilization', 'request_rate', 'context_switches', 'worker_threads']
        for col in required_cols:
            if col not in df.columns:
                raise HTTPException(status_code=400, detail=f"CSV is missing required column: {col}")

        logger.info(f"Successfully processed uploaded CSV telemetry file. Rows: {len(df)}")
        return {"status": "success", "message": f"Successfully loaded telemetry logs ({len(df)} records)"}
    except Exception as e:
        logger.error(f"Error handling CSV upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def run_train_thread(csv_path: str, model_path: str):
    try:
        logger.info("Retraining model in background thread...")
        result = train_model(csv_path, model_path)
        state.load_model()
        logger.info(f"Background retraining successful! Metrics: {result}")
    except Exception as e:
        logger.error(f"Background retraining failed: {e}")

@app.post("/api/train")
def trigger_train(background_tasks: BackgroundTasks):
    if not os.path.exists(CSV_PATH):
        raise HTTPException(status_code=400, detail="Cannot train model: No server_logs.csv found. Please upload a CSV first.")
    
    # Fire off training asynchronously using FastAPI BackgroundTasks
    background_tasks.add_task(run_train_thread, CSV_PATH, MODEL_PATH)
    return {"status": "success", "message": "Model training process initiated in the background."}

# Simulation Paths (Traffic Interception)
@app.get("/browse")
async def browse_endpoint():
    """
    Non-essential browse path. When predictive risk is flagged as HIGH (Governed),
    this path uses Probabilistic Shedding to drop a percentage of requests.
    """
    if state.ai_middleware_active and state.governor_status == "GOVERNED":
        # Probabilistic Shedding: drop 75% of requests to save the server, but let 25% browse
        if np.random.random() < 0.75:
            state.shed_browse += 1
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests", "message": "Intelligent Resource Governor shed request to safeguard Gold Paths."}
            )
    
    # Simulate DB latency/heavy computation
    state.allowed_browse += 1
    # Small simulated db latency
    await asyncio.sleep(state.latency_ms / 1000.0)
    return {"status": "success", "path": "/browse", "message": "Window shopping query successful."}

@app.get("/pay")
async def pay_endpoint():
    """
    Mission-critical transaction path (Gold Path). This bypasses the governor completely.
    """
    state.allowed_pay += 1
    # Checkout is optimized (low latency)
    await asyncio.sleep(0.01) # constant 10ms processing
    return {"status": "success", "path": "/pay", "message": "Checkout transaction completed."}

# WebSocket Endpoint
@app.websocket("/ws/metrics")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.add(websocket)
    logger.info(f"WebSocket connection opened. Active connections: {len(active_websockets)}")
    try:
        while True:
            # Maintain connection alive (client can ping or send messages)
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_websockets.remove(websocket)
        logger.info(f"WebSocket connection closed. Active connections: {len(active_websockets)}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in active_websockets:
            active_websockets.remove(websocket)
