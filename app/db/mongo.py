from app import create_app
from pymongo import MongoClient
from datetime import datetime

# We can access app.mongo if we are within app context, 
# or we can create a new client if needed, but usually we want to reuse the connection.
# However, tasks might run in a separate process (Celery), so we need to be careful.
# The simplest safe way for now without circular imports issues in Celery 
# is to re-establish connection or use the current_app proxy if strictly in Flask context.
# But for Celery tasks, we often need a standalone way or rely on the app context pushed by Celery.

# Let's try to use the pure pymongo client approach for simplicity and robustness in this quick fix,
# reusing the Config.

from app.config import Config

def get_db():
    client = MongoClient(Config.MONGO_URI)
    return client.get_database()

def save_scan_result(result_data):
    db = get_db()
    # verify if result_data has timestamp, if not add it
    if "timestamp" not in result_data:
        result_data["timestamp"] = datetime.utcnow().isoformat()
    
    # We might want to use the task_id or url as a key, but for now just insert
    # If the task passed a task_id, we should store it.
    # The current scan_task.py builds result_data but doesn't explicitly include task_id inside it yet
    # (it returns it). Let's check scan_task.py content again.
    # scan_task.py puts: url, verdict, probability, details, timestamp.
    # We should probably upsert by URL or save as a log. For now, just insert.
    
    db.scan_results.insert_one(result_data)

def get_scan_result(query_filter):
    db = get_db()
    return db.scan_results.find_one(query_filter, {"_id": 0})

def save_batch_info(batch_id, tasks, original_filename):
    """
    tasks: list of dicts like [{"task_id": "...", "url": "..."}]
    """
    db = get_db()
    batch_doc = {
        "batch_id": batch_id,
        "tasks": tasks, 
        "filename": original_filename,
        "created_at": datetime.utcnow().isoformat()
    }
    db.batches.insert_one(batch_doc)

def get_batch_info(batch_id):
    db = get_db()
    return db.batches.find_one({"batch_id": batch_id}, {"_id": 0})

def get_batch_results(batch_id):
    db = get_db()
    batch = db.batches.find_one({"batch_id": batch_id})
    if not batch:
        return None
        
    tasks_meta = batch.get("tasks", []) # List of {task_id, url}
    task_ids = [t["task_id"] for t in tasks_meta]
    
    results_cursor = db.scan_results.find({"task_id": {"$in": task_ids}}, {"_id": 0})
    results = list(results_cursor)
    
    # Map results by task_id for easy lookup
    results_map = {r["task_id"]: r for r in results}
    
    aggregated = []
    for meta in tasks_meta:
        tid = meta["task_id"]
        url = meta["url"]
        res = results_map.get(tid)
        
        if res:
            aggregated.append({
                "task_id": tid,
                "status": "done",
                "result": res
            })
        else:
            # We insert a partial result so UI has the URL
            aggregated.append({
                "task_id": tid,
                "status": "processing",
                "result": {"url": url} 
            })
            
    return {
        "batch_id": batch_id,
        "filename": batch.get("filename"),
        "total": len(tasks_meta),
        "completed": len(results),
        "tasks": aggregated
    }

