import sys
import os

# Replace 'YOUR_USERNAME' with your PythonAnywhere username
path = '/home/YOUR_USERNAME/pilar_beta'
if path not in sys.path:
    sys.path.insert(0, path)

# Set environment variables here (or use a .env file approach)
os.environ.setdefault('SECRET_KEY',       'change-me-in-production')
os.environ.setdefault('ADMIN_PASSWORD',   'pilar-admin-2026')
os.environ.setdefault('BASE_URL',         'https://YOUR_USERNAME.pythonanywhere.com')
os.environ.setdefault('DOWNLOAD_URL',     'https://github.com/CYPHr007/PILAR/releases/download/v1.5.1/PILAR_Setup_1.5.1.exe')
# os.environ.setdefault('GMAIL_ADDRESS',  'you@gmail.com')
# os.environ.setdefault('GMAIL_APP_PASS', 'xxxx xxxx xxxx xxxx')
# os.environ.setdefault('NOTIFY_EMAIL',   'you@gmail.com')

from app import app as application
