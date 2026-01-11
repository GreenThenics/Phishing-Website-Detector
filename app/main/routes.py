from flask import Blueprint, request, jsonify, render_template, current_app
from app.tasks.scan_task import run_scan, perform_scan
from app.db.mongo import get_scan_result, save_batch_info, get_batch_results
import threading
import uuid

main_bp = Blueprint("main", __name__)

@main_bp.route("/scan", methods=["POST"])
def scan_url():
    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL required"}), 400

    print(f"Received scan request for: {url}")
    try:
        # Generate ID manually since we aren't using Celery
        task_id = str(uuid.uuid4())
        print(f"Starting background thread for task {task_id}...")
        
        # Capture the real application object to pass to the thread
        app = current_app._get_current_object()

        # Wrapper to run scan within app context
        def async_scan(url, task_id, app_instance):
            with app_instance.app_context():
                perform_scan(url, task_id)
        
        # Run scan in a separate thread
        thread = threading.Thread(target=async_scan, args=(url, task_id, app))
        thread.start()
        
        return jsonify({
            "task_id": task_id,
            "status": "processing"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to start scan: {str(e)}"}), 500

@main_bp.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@main_bp.route("/api/result/<task_id>", methods=["GET"])
def get_result(task_id):
    # Try to fetch from DB
    result = get_scan_result({"task_id": task_id})
    if result:
        return jsonify({"status": "ready", "result": result})
    else:
        # Check celery status if we wanted to be robust, but for now just say processing or not found
        # In a real app we'd check AsyncResult(task_id).state
        return jsonify({"status": "processing"}), 202

@main_bp.route("/api/progress/<task_id>", methods=["GET"])
def get_progress_status(task_id):
    from app.utils.progress import get_progress
    return jsonify(get_progress(task_id))

@main_bp.route("/result/<task_id>", methods=["GET"])
def show_result(task_id):
    return render_template("result.html", task_id=task_id)

@main_bp.route("/scan/batch", methods=["POST"])
def scan_batch():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if file:
        try:
            content = file.read().decode('utf-8')
            urls = [line.strip() for line in content.splitlines() if line.strip()]
            
            if not urls:
                 return jsonify({"error": "File is empty or no valid URLs found"}), 400
                 
            batch_id = str(uuid.uuid4())
            task_ids = []
            app = current_app._get_current_object()
            
            print(f"Starting batch scan for {len(urls)} URLs. Batch ID: {batch_id}")
            
            for url in urls:
                task_id = str(uuid.uuid4())
                task_ids.append({"task_id": task_id, "url": url})
                
                # Wrapper to run scan within app context
                def async_scan(url, task_id, app_instance):
                    with app_instance.app_context():
                        perform_scan(url, task_id)
                
                # Run scan in a separate thread
                thread = threading.Thread(target=async_scan, args=(url, task_id, app))
                thread.start()
                
            save_batch_info(batch_id, task_ids, file.filename)
            
            return jsonify({
                "batch_id": batch_id,
                "message": f"Started scanning {len(urls)} URLs",
                "url_count": len(urls)
            })
        except Exception as e:
            print(f"Batch scan error: {e}")
            return jsonify({"error": f"Failed to process file: {str(e)}"}), 500
        
    return jsonify({"error": "Invalid file"}), 400

@main_bp.route("/api/batch/<batch_id>", methods=["GET"])
def get_batch_status_api(batch_id):
    results = get_batch_results(batch_id)
    if not results:
        return jsonify({"error": "Batch not found"}), 404
    return jsonify(results)

@main_bp.route("/batch/<batch_id>", methods=["GET"])
def view_batch_result(batch_id):
    return render_template("batch_result.html", batch_id=batch_id)
