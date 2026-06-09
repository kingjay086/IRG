import os
import json
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, classification_report, ConfusionMatrixDisplay

# Setup paths
WORKSPACE_DIR = r"C:\Users\Divya Mohan Nayak\OneDrive\Desktop\New folder"
ARTIFACT_DIR = r"C:\Users\Divya Mohan Nayak\.gemini\antigravity-ide\brain\e51c0a55-87af-4fc1-8df9-b7f3b0a217f7"

# 1. Generate Synthetic Server Telemetry Logs
print("Generating synthetic telemetry data...")
np.random.seed(42)
duration = 1800 # 30 minutes of 1-second interval metrics
timestamps = np.arange(duration)

# Baseline resource values
cpu = np.random.uniform(15, 30, size=duration)
ram = np.random.uniform(35, 45, size=duration)
req_rate = np.random.uniform(5, 15, size=duration)
context_switches = cpu * 25 + np.random.uniform(200, 500, size=duration)
worker_threads = np.random.randint(5, 10, size=duration)
latency = np.random.uniform(5, 15, size=duration)

# Introduce systematic traffic spikes simulating high concurrency
# Spike 1: t=400 to t=700 (duration 300s)
# Spike 2: t=1100 to t=1400 (duration 300s)
for t in range(duration):
    if 400 <= t < 700:
        factor = (t - 400) / 150.0 if t < 550 else (700 - t) / 150.0
        cpu[t] += factor * 60 + np.random.uniform(0, 10)
        ram[t] += (t - 400) * 0.12 # RAM leaks during spike
        req_rate[t] += factor * 180 + np.random.uniform(0, 20)
        worker_threads[t] += int(factor * 25)
        context_switches[t] += factor * 5000 + np.random.uniform(0, 500)
        latency[t] += np.exp(factor * 4.5) * 5
    elif 1100 <= t < 1400:
        factor = (t - 1100) / 150.0 if t < 1250 else (1400 - t) / 150.0
        cpu[t] += factor * 55 + np.random.uniform(0, 10)
        ram[t] += (t - 1100) * 0.15 # Higher RAM leak
        req_rate[t] += factor * 160 + np.random.uniform(0, 20)
        worker_threads[t] += int(factor * 22)
        context_switches[t] += factor * 4500 + np.random.uniform(0, 500)
        latency[t] += np.exp(factor * 4.5) * 5

    # Bound metrics to realistic values
    cpu[t] = min(cpu[t], 99.5)
    ram[t] = min(ram[t], 98.0)
    latency[t] = max(min(latency[t], 2500.0), 3.0)

df = pd.DataFrame({
    'timestamp': timestamps,
    'cpu_utilization': cpu,
    'ram_utilization': ram,
    'request_rate': req_rate,
    'context_switches': context_switches,
    'worker_threads': worker_threads,
    'latency_ms': latency
})

# Predictive Labeling:
# Label y = 1 if CPU > 80% or RAM > 80% or latency_ms > 200ms within the next 30 seconds
y = []
lead_window = 30
for i in range(len(df)):
    future_window = df.iloc[i+1 : min(i+1+lead_window, len(df))]
    if len(future_window) > 0 and (
        (future_window['cpu_utilization'] > 80.0).any() or 
        (future_window['ram_utilization'] > 80.0).any() or
        (future_window['latency_ms'] > 200.0).any()
    ):
        y.append(1)
    else:
        # Check current state as well
        if df.iloc[i]['cpu_utilization'] > 80.0 or df.iloc[i]['ram_utilization'] > 80.0:
            y.append(1)
        else:
            y.append(0)

df['label'] = y

csv_path = os.path.join(WORKSPACE_DIR, 'server_logs.csv')
df.to_csv(csv_path, index=False)
print(f"Telemetry logs saved to: {csv_path}")

# 2. Train Random Forest Classifier
print("Training Random Forest Classifier model...")
features = ['cpu_utilization', 'ram_utilization', 'request_rate', 'context_switches', 'worker_threads']
X = df[features]
y = df['label']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)
model = RandomForestClassifier(n_estimators=50, random_state=42)
model.fit(X_train, y_train)

# Save serialized model artifact
model_path = os.path.join(WORKSPACE_DIR, 'governor_model.pkl')
joblib.dump(model, model_path)
print(f"Governor model serialized to: {model_path}")

# 3. Generate Analytics Plots
print("Generating evaluation plots...")

# Feature Importance
importances = model.feature_importances_
indices = np.argsort(importances)
plt.style.use('dark_background')

plt.figure(figsize=(10, 5))
plt.title('Feature Importances for Server Instability Prediction')
plt.barh(range(len(indices)), importances[indices], color='#3b82f6', align='center')
plt.yticks(range(len(indices)), [features[i] for i in indices])
plt.xlabel('Relative Importance')
plt.tight_layout()

# Save feature importance
feat_imp_ws = os.path.join(WORKSPACE_DIR, 'feature_importance.png')
feat_imp_art = os.path.join(ARTIFACT_DIR, 'feature_importance.png')
plt.savefig(feat_imp_ws, dpi=300)
plt.savefig(feat_imp_art, dpi=300)
plt.close()
print(f"Feature importance plots saved to workspace and artifact directory.")

# Confusion Matrix
y_pred = model.predict(X_test)
cm = confusion_matrix(y_test, y_pred)
disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=['Stable', 'Governed'])

plt.figure(figsize=(6, 6))
disp.plot(cmap=plt.cm.Blues, ax=plt.gca(), colorbar=False)
plt.title('Confusion Matrix: Predictive Load Shedder')
plt.tight_layout()

cm_ws = os.path.join(WORKSPACE_DIR, 'confusion_matrix.png')
cm_art = os.path.join(ARTIFACT_DIR, 'confusion_matrix.png')
plt.savefig(cm_ws, dpi=300)
plt.savefig(cm_art, dpi=300)
plt.close()
print(f"Confusion matrix plots saved to workspace and artifact directory.")

print("Report Metrics:")
print(classification_report(y_test, y_pred))

# 4. Generate Jupyter Notebook JSON
notebook_content = {
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# Intelligent Resource Governor (IRG) - Analytics & Validation Engine\n",
    "\n",
    "This notebook acts as the academic and statistical sandbox for validating the Predictive Edge Middleware. It processes historical resource telemetry datasets, calculates system overload risks, trains the governing brain (Random Forest Classifier), and evaluates model features."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 1. Imports and Setup"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "import numpy as np\n",
    "import pandas as pd\n",
    "import matplotlib.pyplot as plt\n",
    "import joblib\n",
    "from sklearn.ensemble import RandomForestClassifier\n",
    "from sklearn.model_selection import train_test_split\n",
    "from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay\n",
    "\n",
    "plt.style.use('seaborn-v0_8-darkgrid' if 'seaborn-v0_8-darkgrid' in plt.style.available else 'ggplot')\n",
    "print(\"Libraries imported successfully.\")"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 2. Load Telemetry Data\n",
    "We load the generated `server_logs.csv` dataset capturing CPU utilization, Memory allocations, and response metrics."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "df = pd.read_csv('server_logs.csv')\n",
    "df.head(10)"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 3. Exploratory Data Analysis\n",
    "Plot the telemetry variables (CPU, Memory, Latency) across the 30-minute timeline, displaying where resource exhaustion points occur."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)\n",
    "\n",
    "axes[0].plot(df['timestamp'], df['cpu_utilization'], color='tab:red', label='CPU %')\n",
    "axes[0].axhline(80, color='red', linestyle='--', label='80% Stress Threshold')\n",
    "axes[0].set_ylabel('CPU Utilization (%)')\n",
    "axes[0].legend(loc='upper right')\n",
    "axes[0].set_title('Infrastructure Load Telemetry')\n",
    "\n",
    "axes[1].plot(df['timestamp'], df['ram_utilization'], color='tab:blue', label='RAM %')\n",
    "axes[1].axhline(80, color='blue', linestyle='--')\n",
    "axes[1].set_ylabel('RAM Utilization (%)')\n",
    "axes[1].legend(loc='upper right')\n",
    "\n",
    "axes[2].plot(df['timestamp'], df['latency_ms'], color='tab:orange', label='Latency (ms)')\n",
    "axes[2].set_ylabel('Response Latency (ms)')\n",
    "axes[2].set_xlabel('Elapsed Time (Seconds)')\n",
    "axes[2].legend(loc='upper right')\n",
    "\n",
    "plt.tight_layout()\n",
    "plt.show()"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 4. Train Predictive Model\n",
    "Split features and labels, train the Random Forest Classifier, and export the binary model file `governor_model.pkl`."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "features = ['cpu_utilization', 'ram_utilization', 'request_rate', 'context_switches', 'worker_threads']\n",
    "X = df[features]\n",
    "y = df['label']\n",
    "\n",
    "X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)\n",
    "model = RandomForestClassifier(n_estimators=50, random_state=42)\n",
    "model.fit(X_train, y_train)\n",
    "\n",
    "joblib.dump(model, 'governor_model.pkl')\n",
    "print(\"Model trained and serialized as 'governor_model.pkl'.\")"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 5. Model Evaluation and Insights"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "y_pred = model.predict(X_test)\n",
    "print(\"Classification Report:\")\n",
    "print(classification_report(y_test, y_pred))"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "disp = ConfusionMatrixDisplay.from_estimator(model, X_test, y_test, display_labels=['Stable', 'Governed'], cmap=plt.cm.Blues)\n",
    "plt.title('Predictive Governor Confusion Matrix')\n",
    "plt.grid(False)\n",
    "plt.show()"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "importances = model.feature_importances_\n",
    "indices = np.argsort(importances)\n",
    "\n",
    "plt.figure(figsize=(10, 5))\n",
    "plt.title('Feature Importances for Infrastructure Failure Risk')\n",
    "plt.barh(range(len(indices)), importances[indices], color='tab:blue', align='center')\n",
    "plt.yticks(range(len(indices)), [features[i] for i in indices])\n",
    "plt.xlabel('Relative Importance')\n",
    "plt.tight_layout()\n",
    "plt.show()"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3 (ipykernel)",
   "language": "python",
   "name": "python3"
  },
  "language_info": {
   "name": "python"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 2
}

notebook_path = os.path.join(WORKSPACE_DIR, 'research_sandbox.ipynb')
with open(notebook_path, 'w') as f:
    json.dump(notebook_content, f, indent=1)
print(f"Jupyter Notebook successfully written to: {notebook_path}")
