import joblib
import numpy as np
from flask import current_app
from app.services.feature_extractor import extract_url_features, get_ssl_details, scan_html_content, extract_hostname, normalize_url, extract_domain_features

_model = None

def load_model():
    global _model
    if _model is None:
        model_path = current_app.config.get("MODEL_PATH", "model/model.pkl")
        try:
            _model = joblib.load(model_path)
        except FileNotFoundError:
            # If loaded from a different context or file missing, try absolute path or error gracefully
            import os
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
            model_path_abs = os.path.join(base_dir, "model", "model.pkl")
            if os.path.exists(model_path_abs):
                _model = joblib.load(model_path_abs)
            else:
                raise Exception("Model file not found. Please train the model first.")
                
    return _model

def hybrid_predict(target_url, task_id=None):
    """
    Combines URL ML Model with SSL and HTML heuristics.
    """
    from app.utils.progress import update_progress
    print(f"DEBUG: hybrid_predict start for {target_url}")
    target_url = normalize_url(target_url)
    hostname = extract_hostname(target_url)
    
    print(f"Analyzing: {target_url}")

    # 1. URL Model Prediction
    print("DEBUG: Loading model and extracting URL features...")
    if task_id:
        update_progress(task_id, "Loading ML model...", 30)
    model = load_model()
    url_features = extract_url_features(target_url)
    X = np.array(url_features).reshape(1, -1)
    
    # Get probability of being phishing (class 1)
    url_risk = model.predict_proba(X)[0][1] # 0.0 to 1.0
    print(f"DEBUG: URL Risk calculated: {url_risk}")
    if task_id:
        update_progress(task_id, "Analyzing SSL certificate...", 50)

    # 2. SSL Analysis
    print("DEBUG: Starting SSL analysis...")
    ssl_data = get_ssl_details(hostname)
    print("DEBUG: SSL analysis done")
    if task_id:
        update_progress(task_id, "Checking domain information...", 65)
    
    # 3. Domain Analysis (Whois)
    print("DEBUG: Starting Domain/Whois analysis...")
    domain_data = extract_domain_features(target_url)
    print("DEBUG: Domain analysis done")
    if task_id:
        update_progress(task_id, "Scanning page content...", 80)

    # 4. HTML Analysis
    print("DEBUG: Starting HTML content analysis...")
    html = scan_html_content(target_url)
    print("DEBUG: HTML analysis done")
    
    # 5. Risk Scoring (Hybrid Logic)
    ssl_risk = 1 if ssl_data["valid"] == 0 else (
        0.5 if ssl_data["age"] < 15 else 0
    )
    
    domain_risk = 0
    if domain_data["domain_age_days"] >= 0:  # Only assess risk if WHOIS data is available
        if domain_data["domain_age_days"] < 30:  # Very new domain (< 1 month)
            domain_risk = 0.8
        elif domain_data["domain_age_days"] < 180:  # < 6 months
            domain_risk = 0.3
        
    html_risk = 0
    if html["suspicious_form"]:
        html_risk = 1
    elif html["js_rendered"] and url_risk > 0.6:
        html_risk = 0.5

    # Weighted Average
    # Adjust weights to prioritize strong signals (Domain Age, SSL)
    base_risk_score = (
        url_risk * 0.20 +
        domain_risk * 0.30 +
        ssl_risk * 0.30 +
        html_risk * 0.20
    )
    
    # Safety check: If SSL is valid from a trusted issuer (not self-signed),
    # and no suspicious forms, apply a massive discount to avoid FPs on big sites
    trusted_issuers = ["Let's Encrypt", "Google", "DigiCert", "GeoTrust", "WE", "Cloudflare", "Sectigo", "Amazon", "Microsoft"]
    has_trusted_ssl = any(issuer in ssl_data.get("issuer", "") for issuer in trusted_issuers)
    
    if ssl_data["valid"] == 1 and has_trusted_ssl and html["suspicious_form"] == 0:
        # Check for very established domains (e.g., Google, Github)
        if domain_data.get("domain_age_days", 0) > 3650: # > 10 years
             base_risk_score = base_risk_score * 0.1 # 90% discount
        else:
             base_risk_score = base_risk_score * 0.5 # 50% discount
    
    final_risk_score = round(min(base_risk_score * 100, 100), 2)
    
    # Verdict logic
    threshold_high = 75
    threshold_med = 45
    
    if final_risk_score >= threshold_high:
        verdict = "Phishing"
    elif final_risk_score >= threshold_med:
        verdict = "Suspicious"
    else:
        verdict = "Legitimate"

    return {
        "verdict": verdict,
        "probability": final_risk_score,
        "details": {
            "url_risk": round(url_risk * 100, 2),
            "domain_risk": round(domain_risk * 100, 2),
            "ssl_risk": round(ssl_risk * 100, 2),
            "html_risk": round(html_risk * 100, 2),
            "domain_age_days": domain_data["domain_age_days"],
            "creation_date": domain_data.get("creation_date", "Unknown"),
            "ssl_issuer": ssl_data.get("issuer", "Unknown"),
            "registrar": domain_data.get("registrar", "Unknown"),
            "is_ssl_valid": ssl_data["valid"] == 1,
            "has_forms": html["has_forms"] == 1
        }
    }

# Alias for compatibility if needed, but we should use hybrid_predict
def predict(url, task_id=None):
    return hybrid_predict(url, task_id)
