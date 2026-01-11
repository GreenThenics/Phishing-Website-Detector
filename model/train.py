import pandas as pd
import numpy as np
import re
import warnings
import joblib
import os
import tldextract
from urllib.parse import urlparse
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix

warnings.filterwarnings("ignore")

# ==========================================
# UTILITIES (Must match app/services/feature_extractor.py)
# ==========================================

def normalize_url(url):
    url = str(url).strip().lower()
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url

def shannon_entropy(s):
    if not s:
        return 0
    probs = [s.count(c) / len(s) for c in set(s)]
    return -sum(p * np.log2(p) for p in probs)

def extract_url_features(url):
    url = normalize_url(url)
    parsed = urlparse(url)
    
    # Use tldextract for accurate separation
    ext = tldextract.extract(url)
    domain_part = ext.domain
    suffix = ext.suffix
    subdomain = ext.subdomain
    full_domain = f"{subdomain}.{domain_part}.{suffix}".strip(".")

    return [
        len(url),
        url.count("."),
        url.count("/"),
        full_domain.count("-"),
        1 if re.search(r"\d+\.\d+\.\d+\.\d+", full_domain) else 0,
        shannon_entropy(url),
        1 if "@" in url else 0,
        sum(c.isdigit() for c in url) / len(url),
        len(subdomain.split(".")) if subdomain else 0,
        len(suffix),             # TLD length
        1 if "https" in parsed.scheme else 0 # HTTPS check
    ]

# ==========================================
# TRAINING LOGIC (K-Fold + Final Model)
# ==========================================

def train_model():
    print("⏳ Initializing Phishing Detection Model Training (K-Fold)...")

    # Data Paths
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    possible_paths = [
        base_dir, 
        os.path.join(base_dir, "phishing-detector"),
        os.path.join(base_dir, "PDM"),
        r"c:\Users\ADMIN\OneDrive\Desktop\PDM" 
    ]
    
    df = None
    for path in possible_paths:
        try:
            if os.path.exists(os.path.join(path, "legiturl.csv")):
                print(f"Found data in: {path}")
                # Load Datasets
                df1 = pd.read_csv(os.path.join(path, "legiturl.csv"), header=None, names=["url"])
                df1["label"] = 0 # Legitimate
                
                df2 = pd.read_csv(os.path.join(path, "phishydata.csv"), header=None, names=["url"])
                df2["label"] = 1 # Phishing
                
                # Check formatting of new_data.csv
                try:
                    df3 = pd.read_csv(os.path.join(path, "new_data.csv"))
                    if "URLs" in df3.columns and "Labels" in df3.columns:
                         df3 = df3.rename(columns={"URLs": "url", "Labels": "label"})
                except:
                    df3 = pd.DataFrame()

                df = pd.concat([df1, df2, df3], ignore_index=True)
                break
        except Exception as e:
            continue

    if df is not None and not df.empty:
        df = df.dropna().drop_duplicates()
        print(f"✅ Loaded {len(df)} unique samples.")
    else:
        print("⚠ Could not load dataset files. Using DUMMY data.")
        df = pd.DataFrame({
            "url": ["google.com", "amazon.com", "secure-bank-login.com/auth", "free-btc.net"],
            "label": [0, 0, 1, 1]
        })

    print("Extracting features (this may take a moment)...")
    # Extract features for all URLs
    X = np.array([extract_url_features(u) for u in df["url"]])
    y = df["label"].values.astype(int)

    # Stratified K-Fold Cross-Validation
    k = 5
    skf = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)
    
    print(f"\n🔄 Starting {k-1}-Fold Cross-Validation...")
    
    fold = 1
    metrics = {"precision": [], "recall": [], "f1": []}

    for train_index, val_index in skf.split(X, y):
        X_train, X_val = X[train_index], X[val_index]
        y_train, y_val = y[train_index], y[val_index]

        # Training
        clf = RandomForestClassifier(n_estimators=100, random_state=42, class_weight="balanced")
        clf.fit(X_train, y_train)
        
        # Validation
        y_pred = clf.predict(X_val)
        
        p = precision_score(y_val, y_pred, zero_division=0)
        r = recall_score(y_val, y_pred, zero_division=0)
        f = f1_score(y_val, y_pred, zero_division=0)
        
        metrics["precision"].append(p)
        metrics["recall"].append(r)
        metrics["f1"].append(f)
        
        print(f"   Fold {fold}: Precision={p:.4f}, Recall={r:.4f}, F1={f:.4f}")
        fold += 1

    # Average Metrics
    print("\n📊 Cross-Validation Results (Average):")
    print(f"   Precision: {np.mean(metrics['precision']):.4f} ± {np.std(metrics['precision']):.4f}")
    print(f"   Recall:    {np.mean(metrics['recall']):.4f} ± {np.std(metrics['recall']):.4f}")
    print(f"   F1-Score:  {np.mean(metrics['f1']):.4f} ± {np.std(metrics['f1']):.4f}")

    # Final Training on Full Dataset
    print("\n🚀 Training Final Model on 100% Data...")
    final_model = RandomForestClassifier(n_estimators=150, random_state=42, class_weight="balanced")
    final_model.fit(X, y)

    # Save Model
    output_path = os.path.join(os.path.dirname(__file__), 'model.pkl')
    joblib.dump(final_model, output_path)
    print(f"✅ Final Model saved to: {output_path}")

if __name__ == "__main__":
    train_model()
