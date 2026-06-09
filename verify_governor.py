import subprocess
import time
import urllib.request
import urllib.parse
import json
import sys

def send_request(path: str, method: str = "GET", data: dict = None) -> tuple:
    url = f"http://127.0.0.1:8088{path}"
    headers = {"Content-Type": "application/json"}
    
    req_data = None
    if data:
        req_data = json.dumps(data).encode("utf-8")
        
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"error": e.reason}
    except Exception as e:
        return 500, {"error": str(e)}

def main():
    print("=========================================================")
    print("  INTELLIGENT RESOURCE GOVERNOR SYSTEM VERIFICATION RUN  ")
    print("=========================================================\n")
    
    # 1. Start FastAPI server as a background subprocess
    print("[1/5] Booting FastAPI backend application...")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8088"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for FastAPI and Uvicorn to boot up
    time.sleep(3)
    
    if server_process.poll() is not None:
        print("ERROR: FastAPI server failed to start. Check ports or logs.")
        stdout, stderr = server_process.communicate()
        print("Stdout:", stdout)
        print("Stderr:", stderr)
        sys.exit(1)
        
    try:
        # 2. Verify Initial Config State
        print("[2/5] Inspecting default dashboard configuration state...")
        code, state = send_request("/api/state")
        assert code == 200, f"Failed to query state endpoint: HTTP {code}"
        assert state["ai_middleware_active"] is False, "Expected AI Middleware to be deactivated initially"
        assert state["simulate_load_spike"] is False, "Expected load spike simulation to be deactivated initially"
        print("Success: Initial idle state verified.")

        # 3. Test Routing under Normal Idle conditions
        print("\n[3/5] Simulating user traffic under normal conditions...")
        code, browse_res = send_request("/browse")
        assert code == 200, f"Expected /browse HTTP 200, got: HTTP {code}"
        print(f" - /browse: HTTP {code} | {browse_res.get('message')}")
        
        code, pay_res = send_request("/pay")
        assert code == 200, f"Expected /pay HTTP 200, got: HTTP {code}"
        print(f" - /pay:    HTTP {code} | {pay_res.get('message')}")
        print("Success: All paths allow traffic normally.")

        # 4. Test Load Spikes without AI Governor Middleware
        print("\n[4/5] Activating traffic load spike simulation (AI Gate OFF)...")
        code, spike_toggle = send_request("/api/toggle-spike", "POST", {"value": True})
        assert code == 200, "Failed to toggle load spike simulator"
        
        print(" - Accumulating traffic concurrency load (waiting 4 seconds)...")
        time.sleep(4)
        
        code, state = send_request("/api/state")
        print(f" - System telemetry state: Status={state['governor_status']}")
        
        print(" - Testing route accessibility during raw resource saturation:")
        code, browse_res = send_request("/browse")
        assert code == 200, f"Expected /browse to accept requests without middleware, got: HTTP {code}"
        print(f"   - /browse: HTTP {code} (Allowed, but experiencing latency)")
        print("Success: Server remains unprotected; traffic allowed to cascade.")

        # 5. Enable AI Middleware and verify load shedding
        print("\n[5/5] Deploying Predictive Edge AI Middleware Gate (AI Gate ON)...")
        code, ai_toggle = send_request("/api/toggle-middleware", "POST", {"value": True})
        assert code == 200, "Failed to deploy AI Middleware"
        
        print(" - Running model predictions on telemetry changes (waiting 2 seconds)...")
        time.sleep(2)
        
        code, state = send_request("/api/state")
        print(f" - System telemetry state: Status={state['governor_status']}")
        
        # We expect the state to be GOVERNED
        assert state["governor_status"] == "GOVERNED", "Model failed to classify load spike instability"
        
        print(" - Testing /browse load shedding (Deferred Path):")
        code, browse_res = send_request("/browse")
        assert code == 429, f"Expected /browse to shed (HTTP 429) under stress, got: HTTP {code}"
        print(f"   - /browse: HTTP {code} (Shed successfully!) | {browse_res.get('error')}: {browse_res.get('message')}")
        
        print(" - Testing /pay transaction preservation (Gold Path):")
        code, pay_res = send_request("/pay")
        assert code == 200, f"Expected /pay Gold Path to be 100% active, got: HTTP {code}"
        print(f"   - /pay:    HTTP {code} (Gold Path Preserved) | {pay_res.get('message')}")
        
        # Reset switches
        print("\nResetting simulation states to defaults...")
        send_request("/api/toggle-spike", "POST", {"value": False})
        send_request("/api/toggle-middleware", "POST", {"value": False})
        
        print("\n=========================================================")
        print("  VERIFICATION SUCCESS: ALL 5 SYSTEM SCENARIOS PASSED!  ")
        print("=========================================================")

    except AssertionError as ae:
        print(f"\nVERIFICATION FAIL: {ae}")
        # Make sure to reset switches
        send_request("/api/toggle-spike", "POST", {"value": False})
        send_request("/api/toggle-middleware", "POST", {"value": False})
        sys.exit(1)
    finally:
        print("Shutting down backend subprocess...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("Server shutdown clean.")

if __name__ == "__main__":
    main()
