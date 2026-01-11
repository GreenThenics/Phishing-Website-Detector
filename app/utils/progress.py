"""
Simple in-memory progress tracker for scan tasks.
"""

progress_store = {}

def update_progress(task_id, message, percentage=None):
    """Update progress for a task."""
    progress_store[task_id] = {
        "message": message,
        "percentage": percentage,
        "timestamp": __import__('datetime').datetime.utcnow().isoformat()
    }

def get_progress(task_id):
    """Get progress for a task."""
    return progress_store.get(task_id, {"message": "Starting scan...", "percentage": 0})

def clear_progress(task_id):
    """Clear progress for a task."""
    if task_id in progress_store:
        del progress_store[task_id]
