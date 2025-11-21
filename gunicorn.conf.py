# Gunicorn configuration for Raspberry Pi 5
import os

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', 10000)}"
backlog = 2048

# Worker processes
workers = 3 # Raspberry Pi 5 has 4 cores, start with 3 workers for 4GB RAM
worker_class = "uvicorn.workers.UvicornWorker" # Use Uvicorn worker for async app
worker_connections = 1000
timeout = 60 # Increased timeout for potentially longer API calls
keepalive = 2

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process naming
proc_name = "cybershield-backend"

# Server mechanics
daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None

# SSL (Not needed for local deployment)
# keyfile = None
# certfile = None
