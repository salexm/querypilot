import os

# Settings are required at import time, and unit tests never connect with these.
os.environ.setdefault("ANALYTICS_DB_NAME", "analytics")
os.environ.setdefault("ANALYTICS_READONLY_USER", "test_readonly")
os.environ.setdefault("ANALYTICS_READONLY_PASSWORD", "test-password")
