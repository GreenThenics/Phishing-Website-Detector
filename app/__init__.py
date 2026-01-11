from flask import Flask
from celery import Celery
from pymongo import MongoClient
from .config import Config
import os

celery = Celery(__name__)

def create_app():
    # Get the base directory (project root)
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    # Create Flask app with correct template and static folders
    app = Flask(__name__, 
                template_folder=os.path.join(base_dir, 'templates'),
                static_folder=os.path.join(base_dir, 'static'))
    app.config.from_object(Config)

    # Configure Celery explicitly
    celery.conf.task_always_eager = True  # Run tasks synchronously without Redis
    celery.conf.broker_url = app.config["CELERY_BROKER_URL"]
    celery.conf.result_backend = app.config["CELERY_RESULT_BACKEND"]

    mongo_client = MongoClient(app.config["MONGO_URI"])
    app.mongo = mongo_client.get_database()

    from .main.routes import main_bp
    app.register_blueprint(main_bp)

    return app
