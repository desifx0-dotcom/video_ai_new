from src.main import create_app

# create_app() returns (app, socketio)
app, socketio = create_app()

if __name__ == "__main__":
    # Use socketio.run() instead of app.run()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)