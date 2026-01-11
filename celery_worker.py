from app import create_app, celery

app = create_app()
app.app_context().push()

# Import tasks so they are registered with Celery
from app.tasks import scan_task
