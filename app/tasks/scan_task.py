from app import celery
from app.services.precheck import pre_validate
from app.services.ml_model import predict
from app.utils.progress import update_progress
from datetime import datetime

# Logic extracted for threading support
def perform_scan(url, task_id):
    print(f"DEBUG: Task started for {url}")
    update_progress(task_id, "Validating URL...", 10)
    
    if not pre_validate(url):
        print("DEBUG: Pre-validation failed")
        return {"error": "Pre-validation failed"}

    try:
        print("DEBUG: Calling predict()...")
        update_progress(task_id, "Analyzing URL...", 20)
        result = predict(url, task_id)
        print("DEBUG: Prediction complete")
        update_progress(task_id, "Finalizing results...", 95)
    except Exception as e:
        print(f"DEBUG: Prediction failed: {e}")
        error_result = {
            "task_id": task_id,
            "url": url,
            "error": str(e),
            "verdict": "Error",
            "probability": 0,
            "timestamp": datetime.utcnow().isoformat()
        }
        from app.db.mongo import save_scan_result
        save_scan_result(error_result)
        return error_result

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

@celery.task(bind=True)
def run_scan(self, url):
    return perform_scan(url, self.request.id)
