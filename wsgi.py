import sys
import os

path = '/home/k4kut4/pilar_beta'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ.setdefault('SECRET_KEY',       'Rz9pXw2mKqL7vN4tYjBsU1eAhCdFgOi')
os.environ.setdefault('ADMIN_PASSWORD',   'SOUSOUhiba2014!')
os.environ.setdefault('ADMIN_PATH',       'PILAR-CEO-2026')
os.environ.setdefault('BASE_URL',         'https://k4kut4.pythonanywhere.com')
os.environ.setdefault('DOWNLOAD_URL',     'https://github.com/CYPHr007/PILAR/releases/download/v1.5.1/PILAR_Setup_1.5.1.exe')
# os.environ.setdefault('GMAIL_ADDRESS',  'you@gmail.com')
# os.environ.setdefault('GMAIL_APP_PASS', 'xxxx xxxx xxxx xxxx')
# os.environ.setdefault('NOTIFY_EMAIL',   'you@gmail.com')

from app import app as application
