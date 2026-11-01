import sys
import os

# Ensure working directory is application directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app_gui import run_app

if __name__ == "__main__":
    run_app()

