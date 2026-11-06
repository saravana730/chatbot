import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-characters-long")
os.environ.setdefault("CSRF_SECRET", "test-csrf-secret-at-least-32-chars")
os.environ.setdefault("BOOTSTRAP_EMAIL", "admin@docchat.com")
os.environ.setdefault("BOOTSTRAP_PASSWORD", "password")
