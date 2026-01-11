from app import celery
from app.services.precheck import pre_validate
from app.services.ml_model import predict
from app.utils.progress import update_progress
from datetime import datetime

import concurrent.futures

from flask import current_app

# Logic extracted for threading support
def perform_scan(url, task_id):
    try:
        print(f"DEBUG: Task started for {url}")
        
        # 1. Scheme Check
        if not url.lower().startswith(('http://', 'https://')):
            msg = "Invalid URL: Missing scheme (http:// or https://)"
            print(f"DEBUG: {msg}")
            error_result = {
                "task_id": task_id,
                "url": url,
                "error": msg,
                "verdict": "Error",
                "probability": 0,
                "timestamp": datetime.utcnow().isoformat()
            }
            # Import inside to avoid circular dependency issues during startup
            from app.db.mongo import save_scan_result
            save_scan_result(error_result)
            return error_result

        update_progress(task_id, "Validating URL...", 10)
        
        # 2. General Validation
        if not pre_validate(url):
            msg = "Pre-validation failed: Malformed URL"
            print(f"DEBUG: {msg}")
            error_result = {
                "task_id": task_id,
                "url": url,
                "error": msg,
                "verdict": "Error",
                "probability": 0,
                "timestamp": datetime.utcnow().isoformat()
            }
            from app.db.mongo import save_scan_result
            save_scan_result(error_result)
            return {"error": msg}

        print("DEBUG: Calling predict()...")
        update_progress(task_id, "Analyzing URL...", 20)
        
        # Capture app for thread context
        app = current_app._get_current_object()
        
        def predict_with_context(u, t):
            with app.app_context():
                return predict(u, t)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(predict_with_context, url, task_id)
            try:
                result = future.result(timeout=60)
            except concurrent.futures.TimeoutError:
                raise TimeoutError("Scan timed out (60s limit exceeded)")

        print("DEBUG: Prediction complete")
        update_progress(task_id, "Finalizing results...", 95)
        
        result_data = {
            "task_id": task_id,
            "url": url,
            "verdict": result["verdict"],
            "probability": result["probability"],
            "details": result.get("details", {}),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Save to MongoDB
        from app.db.mongo import save_scan_result
        try:
            save_scan_result(result_data)
            update_progress(task_id, "Scan complete!", 100)
        except Exception as e:
            print(f"Warning: Failed to save to MongoDB: {e}")
            result_data["db_error"] = str(e)

        return result_data

    except Exception as e:
        print(f"CRITICAL ERROR in perform_scan: {e}")
        import traceback
        traceback.print_exc()
        
        error_result = {
            "task_id": task_id,
            "url": url,
            "error": str(e),
            "verdict": "Error",
            "probability": 0,
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            from app.db.mongo import save_scan_result
            save_scan_result(error_result)
        except Exception as db_e:
            print(f"Double fault: Failed to save error to DB: {db_e}")
        
        return error_result

@celery.task(bind=True)
def run_scan(self, url):
    return perform_scan(url, self.request.id)
