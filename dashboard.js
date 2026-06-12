// Intelligent Resource Governor Dashboard Logic
const BACKEND_HOST = window.location.hostname || "localhost";
const API_URL = `http://${BACKEND_HOST}:8088/api`;
const WS_URL = `ws://${BACKEND_HOST}:8088/ws/metrics`;

// UI Elements
const statusBadge = document.getElementById("system-status-badge");
const statusText = document.getElementById("system-status-text");
const aiToggle = document.getElementById("ai-middleware-toggle");
const spikeToggle = document.getElementById("load-spike-toggle");
const retrainBtn = document.getElementById("retrain-model-btn");

// Live Gauge Elements
const cpuCircle = document.getElementById("gauge-cpu-circle");
const cpuVal = document.getElementById("gauge-cpu-val");
const ramCircle = document.getElementById("gauge-ram-circle");
const ramVal = document.getElementById("gauge-ram-val");
const latencyVal = document.getElementById("gauge-latency-val");
const requestVal = document.getElementById("gauge-request-val");

// Transaction Stream Counts
const payCount = document.getElementById("metrics-allowed-pay");
const browseCount = document.getElementById("metrics-allowed-browse");
const shedCount = document.getElementById("metrics-shed-browse");

// Drag & Drop
const dropZone = document.getElementById("drag-drop-zone");
const fileInput = document.getElementById("csv-file-input");
const progressContainer = document.getElementById("upload-progress-container");
const progressBar = document.getElementById("upload-progress-bar");
const historicalCanvasSection = document.getElementById("historical-canvas-section");

// Charts Setup
let liveChart = null;
let histChart = null;

// Global settings
const MAX_LIVE_POINTS = 30;
const CIRCUMFERENCE = 2 * Math.PI * 50; // 314.159 for r=50 circle

// Initialize Rolling Live Chart
function initLiveChart() {
  const ctx = document.getElementById("live-rolling-chart").getContext("2d");
  
  const initialLabels = Array(MAX_LIVE_POINTS).fill("");
  const initialData = Array(MAX_LIVE_POINTS).fill(0);
  
  liveChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: initialLabels,
      datasets: [
        {
          label: "CPU Utilization (%)",
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59, 130, 246, 0.1)",
          borderWidth: 2,
          pointRadius: 0,
          data: [...initialData],
          tension: 0.3
        },
        {
          label: "RAM Utilization (%)",
          borderColor: "#8b5cf6",
          backgroundColor: "rgba(139, 92, 246, 0.05)",
          borderWidth: 2,
          pointRadius: 0,
          data: [...initialData],
          tension: 0.3
        },
        {
          label: "Governed State Indicator",
          borderColor: "transparent",
          backgroundColor: "rgba(239, 68, 68, 0.15)",
          fill: true,
          borderWidth: 0,
          pointRadius: 0,
          data: [...initialData],
          tension: 0,
          stepped: true
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: "#94a3b8", font: { family: "Inter", size: 11 } }
        }
      },
      scales: {
        x: {
          grid: { display: false }
        },
        y: {
          min: 0,
          max: 100,
          ticks: { color: "#94a3b8", font: { family: "Inter" } },
          grid: { color: "rgba(255, 255, 255, 0.05)" }
        }
      }
    }
  });
}

// Update Circular Gauge
function updateGauge(circleElement, valueTextElement, value) {
  const valFloat = parseFloat(value);
  valueTextElement.textContent = `${valFloat.toFixed(1)}%`;
  
  // Update stroke offset
  const offset = CIRCUMFERENCE - (valFloat / 100) * CIRCUMFERENCE;
  circleElement.style.strokeDashoffset = offset;
}

// Fetch Initial State from APIs
async function fetchInitialState() {
  try {
    const res = await fetch(`${API_URL}/state`);
    const data = await res.json();
    aiToggle.checked = data.ai_middleware_active;
    spikeToggle.checked = data.simulate_load_spike;
    updateStatusBadge(data.governor_status);
  } catch (err) {
    console.error("Failed to load initial server state:", err);
  }
}

// Update UI Badge based on governor state
function updateStatusBadge(status) {
  if (status === "GOVERNED") {
    statusBadge.className = "system-badge governed";
    statusText.textContent = "GOVERNED STATE";
    dropZone.classList.add("pulse-red-glow");
    dropZone.classList.remove("pulse-green-glow");
  } else {
    statusBadge.className = "system-badge stable";
    statusText.textContent = "STABLE STATE";
    dropZone.classList.add("pulse-green-glow");
    dropZone.classList.remove("pulse-red-glow");
  }
}

// Setup WebSocket live stream
let socket = null;
function connectWebSocket() {
  socket = new WebSocket(WS_URL);
  
  socket.onopen = () => {
    console.log("WebSocket stream connected successfully.");
    statusBadge.style.opacity = "1";
  };
  
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    // Update live indicators
    updateGauge(cpuCircle, cpuVal, data.cpu_utilization);
    updateGauge(ramCircle, ramVal, data.ram_utilization);
    
    // Update latency and request rates
    latencyVal.textContent = `${data.latency_ms} ms`;
    requestVal.textContent = `${data.request_rate} rps`;
    
    // Color code latency text based on health thresholds
    if (data.latency_ms > 500) {
      latencyVal.className = "latency-display crit";
    } else if (data.latency_ms > 150) {
      latencyVal.className = "latency-display warn";
    } else {
      latencyVal.className = "latency-display";
    }
    
    // Update counters
    payCount.textContent = data.allowed_pay;
    browseCount.textContent = data.allowed_browse;
    shedCount.textContent = data.shed_browse;
    
    // Update active status badge
    updateStatusBadge(data.governor_status);
    
    // Add point to rolling telemetry chart
    if (liveChart) {
      const labels = liveChart.data.labels;
      const cpuData = liveChart.data.datasets[0].data;
      const ramData = liveChart.data.datasets[1].data;
      const govData = liveChart.data.datasets[2].data;
      
      // Shift left
      labels.shift();
      labels.push(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      
      cpuData.shift();
      cpuData.push(data.cpu_utilization);
      
      ramData.shift();
      ramData.push(data.ram_utilization);
      
      govData.shift();
      govData.push(data.governor_status === "GOVERNED" ? 100 : 0);
      
      liveChart.update("none"); // Performance optimized update
    }
  };
  
  socket.onclose = () => {
    console.warn("WebSocket disconnected. Attempting reconnect in 3s...");
    statusBadge.className = "system-badge";
    statusText.textContent = "DISCONNECTED";
    statusBadge.style.opacity = "0.5";
    setTimeout(connectWebSocket, 3000);
  };
  
  socket.onerror = (err) => {
    console.error("WebSocket error:", err);
    socket.close();
  };
}

// Controller Actions
aiToggle.addEventListener("change", async () => {
  try {
    await fetch(`${API_URL}/toggle-middleware`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value: aiToggle.checked })
    });
  } catch (err) {
    console.error("Error toggling AI middleware:", err);
    aiToggle.checked = !aiToggle.checked; // revert
  }
});

spikeToggle.addEventListener("change", async () => {
  try {
    await fetch(`${API_URL}/toggle-spike`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value: spikeToggle.checked })
    });
  } catch (err) {
    console.error("Error toggling load spike:", err);
    spikeToggle.checked = !spikeToggle.checked; // revert
  }
});

retrainBtn.addEventListener("click", async () => {
  try {
    retrainBtn.disabled = true;
    retrainBtn.innerHTML = `
      <svg class="animate-spin" width="16" height="16" fill="none" viewBox="0 0 24 24" style="animation: spin 1s linear infinite; margin-right: 0.5rem;">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" style="opacity: 0.25;"></circle>
        <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
      Retraining Model...
    `;
    
    // Inject spinning stylesheet keyframe if not present
    if (!document.getElementById("spin-animation-style")) {
      const style = document.createElement("style");
      style.id = "spin-animation-style";
      style.innerText = "@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }";
      document.head.appendChild(style);
    }
    
    const res = await fetch(`${API_URL}/train`, { method: "POST" });
    const data = await res.json();
    
    alert("ML Brain retraining successfully initiated in background thread!");
  } catch (err) {
    console.error("Error retraining model:", err);
    alert("Failed to initiate model retraining.");
  } finally {
    retrainBtn.disabled = false;
    retrainBtn.innerHTML = `
      <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
        <path d="M12 6v3l4-4-4-4v3c-4.42 0-8 3.58-8 8 0 1.57.46 3.03 1.24 4.26L6.7 14.8c-.45-.83-.7-1.79-.7-2.8 0-3.31 2.69-6 6-6zm6.76 1.74L17.3 9.2c.44.84.7 1.79.7 2.8 0 3.31-2.69 6-6 6v-3l-4 4 4 4v-3c4.42 0 8-3.58 8-8 0-1.57-.46-3.03-1.24-4.26z"/>
      </svg>
      Retrain AI Model
    `;
  }
});

// Drag & Drop Ingestion Handler
["dragenter", "dragover"].forEach(eventName => {
  dropZone.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  }, false);
});

["dragleave", "drop"].forEach(eventName => {
  dropZone.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
  }, false);
});

dropZone.addEventListener("drop", (e) => {
  const dt = e.dataTransfer;
  const files = dt.files;
  if (files.length > 0 && files[0].name.endsWith(".csv")) {
    handleCSVUpload(files[0]);
  } else {
    alert("Please upload a valid CSV telemetry file.");
  }
});

dropZone.addEventListener("click", () => {
  fileInput.click();
});

fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) {
    handleCSVUpload(fileInput.files[0]);
  }
});

// File upload and processing
function handleCSVUpload(file) {
  try {
    progressContainer.style.display = "block";
    progressBar.style.width = "10%";
    
    // 1. Instantly parse and render the chart locally so the UI updates immediately!
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        renderHistoricalChart(e.target.result);
      } catch (err) {
        console.error("Error rendering chart:", err);
        alert("Error parsing CSV for the chart: " + err.message);
      }
    };
    reader.readAsText(file);

    // 2. Upload to backend for model retraining
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);
    
    xhr.open("POST", `${API_URL}/upload-csv`, true);
    
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        // Start from 10% to show initial progress
        const percentage = 10 + ((e.loaded / e.total) * 90);
        progressBar.style.width = `${percentage}%`;
      }
    };
    
    xhr.onload = () => {
      progressBar.style.width = "100%";
      setTimeout(() => {
        progressContainer.style.display = "none";
      }, 1000);

      if (xhr.status === 200) {
        try {
          const response = JSON.parse(xhr.responseText);
          alert(response.message || "Successfully loaded telemetry logs!");
        } catch (e) {
          alert("Successfully uploaded, but received invalid JSON response from server.");
        }
      } else {
        console.error(xhr.responseText);
        alert(`Failed to upload to server. Status: ${xhr.status}. See console for details.`);
      }
    };
    
    xhr.onerror = () => {
      progressContainer.style.display = "none";
      alert("Network error occurred while trying to upload the file to the backend.");
    };
    
    xhr.send(formData);
  } catch (err) {
    console.error("Critical error in handleCSVUpload:", err);
    alert("An unexpected error occurred: " + err.message);
  }
}

// Client-side CSV Parser & Historical Chart Renderer
function renderHistoricalChart(csvText) {
  const lines = csvText.split("\n");
  if (lines.length < 2) return;
  
  // Trim headers to remove \r from Windows CRLF files
  const headers = lines[0].split(",").map(h => h.trim());
  const cpuIdx = headers.indexOf("cpu_utilization");
  const ramIdx = headers.indexOf("ram_utilization");
  const latIdx = headers.indexOf("latency_ms");
  const labelIdx = headers.indexOf("label");
  const timeIdx = headers.indexOf("timestamp");
  
  if (cpuIdx === -1 || ramIdx === -1) {
    alert("Uploaded CSV lacks key telemetry variables ('cpu_utilization', 'ram_utilization').");
    return;
  }
  
  const timestamps = [];
  const cpuVals = [];
  const ramVals = [];
  const latVals = [];
  const govStates = [];
  
  // Process rows, limit data points to 200 to keep the graph readable and fast
  const rowStep = Math.max(1, Math.floor(lines.length / 200));
  
  for (let i = 1; i < lines.length; i += rowStep) {
    const row = lines[i].split(",");
    if (row.length < headers.length) continue;
    
    timestamps.push(row[timeIdx] ? `${row[timeIdx]}s` : `${i}s`);
    cpuVals.push(parseFloat(row[cpuIdx]));
    ramVals.push(parseFloat(row[ramIdx]));
    if (latIdx !== -1) latVals.push(parseFloat(row[latIdx]));
    if (labelIdx !== -1) govStates.push(parseInt(row[labelIdx]) === 1 ? 100 : 0);
  }
  
  // Reveal historical dashboard section
  historicalCanvasSection.style.display = "block";
  
  if (histChart) {
    histChart.destroy();
  }
  
  const ctx = document.getElementById("historical-chart").getContext("2d");
  
  const datasets = [
    {
      label: "CPU Utilization (%)",
      borderColor: "#ef4444",
      backgroundColor: "transparent",
      borderWidth: 1.5,
      pointRadius: 0,
      data: cpuVals
    },
    {
      label: "RAM Utilization (%)",
      borderColor: "#8b5cf6",
      backgroundColor: "transparent",
      borderWidth: 1.5,
      pointRadius: 0,
      data: ramVals
    }
  ];
  
  // If label column is available, display it as a background shader
  if (govStates.length > 0) {
    datasets.push({
      label: "Model Classification Boundary (Governed)",
      borderColor: "transparent",
      backgroundColor: "rgba(239, 68, 68, 0.08)",
      fill: true,
      borderWidth: 0,
      pointRadius: 0,
      data: govStates,
      stepped: true
    });
  }
  
  histChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: timestamps,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: "#94a3b8", font: { family: "Inter", size: 11 } }
        }
      },
      scales: {
        x: {
          ticks: { color: "#94a3b8", maxTicksLimit: 15 },
          grid: { display: false }
        },
        y: {
          min: 0,
          max: 100,
          ticks: { color: "#94a3b8" },
          grid: { color: "rgba(255, 255, 255, 0.05)" }
        }
      }
    }
  });
}

// Initial Boot
window.addEventListener("DOMContentLoaded", () => {
  initLiveChart();
  fetchInitialState();
  connectWebSocket();
  
  // Load mock data if server_logs.csv already exists on disk
  fetch(`${API_URL}/state`)
    .then(res => res.json())
    .then(data => {
      // Prompt user to upload or trigger mock CSV render if available
    });
});
