
### **Procfile**
```yaml
# Procfile for process managers (Heroku, Railway, etc.)

web: gunicorn --bind 0.0.0.0:$PORT --workers 4 --worker-class eventlet --timeout 120 --keep-alive 5 app:app
worker: celery -A tasks.celery_app:celery worker --loglevel=info --concurrency=4 --max-tasks-per-child=100
beat: celery -A tasks.celery_app:celery beat --loglevel=info
websocket: python -m src.main

# Alternative configurations:

# For production with more workers:
# web: gunicorn --bind 0.0.0.0:$PORT --workers 8 --worker-class gevent --timeout 120 --keep-alive 5 --access-logfile - --error-logfile - app:app

# For development:
# web: flask run --host=0.0.0.0 --port=$PORT

# For testing:
# test: pytest tests/ --cov=src --cov-report=term-missing

# For database migrations:
# migrate: flask db upgrade