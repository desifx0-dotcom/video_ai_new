#!/usr/bin/env python3
# start.py - Auto-activates venv and starts app
from patch_async import ASYNC_MODE
import os
import sys
import subprocess
# Import and run
from src.main import create_app
from dotenv import load_dotenv

load_dotenv()


def main():
    # Check if we're in the right directory
    if not os.path.exists("src"):
        print("❌ Error: Run this from project root directory")
        sys.exit(1)

    # Check venv activation
    venv_python = os.path.join(".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        print("❌ Virtual environment not found. Creating...")
        subprocess.run([sys.executable, "-m", "venv", ".venv"])



if __name__ == "__main__":
    # Create app ONCE
    app, socketio = create_app()
    
    print("🚀 Starting Video AI Studio...")
    print(f"🌐 Server URL: http://0.0.0.0:5000")
    
    # Run with reloader disabled
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=False,  # Set to True for development
        use_reloader=False,  # Prevent double init
        # allow_unsafe_werkzeug=True  # Only if needed
    )