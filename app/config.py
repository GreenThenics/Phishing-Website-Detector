import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/phishing_db")
    CELERY_BROKER_URL = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND = "redis://localhost:6379/0"
    CELERY_TASK_ALWAYS_EAGER = True # Run locally without Redis for this demo
    MODEL_PATH = "model/model.pkl"
    PHISHING_THRESHOLD = 0.4
