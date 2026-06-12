import os
# pyrefly: ignore [missing-import]
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

def train_model(csv_path: str, model_path: str) -> dict:
    """
    Reads CSV telemetry logs, trains a Random Forest Classifier to predict system instability,
    and serializes the trained model.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Telemetry logs CSV not found at {csv_path}")

    # Load telemetry dataframe
    df = pd.read_csv(csv_path)

    # Required columns validation
    required_cols = ['cpu_utilization', 'ram_utilization', 'request_rate', 'context_switches', 'worker_threads']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Required telemetry feature '{col}' missing from data.")

    # Compute label dynamically if not present
    if 'label' not in df.columns:
        y = []
        lead_window = 30
        for i in range(len(df)):
            future_window = df.iloc[i+1 : min(i+1+lead_window, len(df))]
            if len(future_window) > 0 and (
                (future_window['cpu_utilization'] > 80.0).any() or 
                (future_window['ram_utilization'] > 80.0).any() or
                ('latency_ms' in df.columns and (future_window['latency_ms'] > 200.0).any())
            ):
                y.append(1)
            else:
                if df.iloc[i]['cpu_utilization'] > 80.0 or df.iloc[i]['ram_utilization'] > 80.0:
                    y.append(1)
                else:
                    y.append(0)
        df['label'] = y

    X = df[required_cols]
    y = df['label']

    # Split dataset stratifying target
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y if len(y.unique()) > 1 else None
    )

    # Train Random Forest Classifier
    model = RandomForestClassifier(n_estimators=30, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)

    # Save serialized model artifact
    joblib.dump(model, model_path)

    # Generate metadata metrics
    train_acc = model.score(X_train, y_train)
    test_acc = model.score(X_test, y_test)

    return {
        "status": "success",
        "train_accuracy": float(train_acc),
        "test_accuracy": float(test_acc),
        "total_records": len(df),
        "governed_records": int(y.sum()),
        "stable_records": int(len(df) - y.sum())
    }

if __name__ == "__main__":
    import os
    # Define paths relative to this script
    workspace = os.path.dirname(os.path.abspath(__file__))
    csv_file = os.path.join(workspace, "server_logs.csv")
    model_file = os.path.join(workspace, "governor_model.pkl")
    
    print(f"Starting model training...\nReading from: {csv_file}")
    try:
        results = train_model(csv_file, model_file)
        print("Training completed successfully!")
        print(f"Metrics: {results}")
    except Exception as e:
        print(f"Training failed: {e}")
