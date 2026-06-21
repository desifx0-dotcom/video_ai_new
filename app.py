# app.py
from patch_async import ASYNC_MODE
from src.main import create_app

app, socketio = create_app()

if __name__ == "__main__":

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=False,  # ← Debug False to prevent auto-reloader
        use_reloader=False
    )