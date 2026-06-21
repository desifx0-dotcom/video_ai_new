#!/usr/bin/env python3
# start.py - Auto-activates venv and starts app
from patch_async import ASYNC_MODE
import os
import sys
import subprocess

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

    # Run the app using venv python
    print("🚀 Starting Video AI Studio...")
    subprocess.run([venv_python, "app.py"])


if __name__ == "__main__":
    main()