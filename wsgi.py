import os
import sys

# Tambahkan direktori root proyek ke sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import objek Flask dari app.py sebagai 'application' (standar WSGI)
from app import app as application

if __name__ == "__main__":
    application.run()
