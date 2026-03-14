from python:3.11-slim

# install system dependencies for snowflake-snowpark-python
run apt-get update && apt-get install -y --no-install-recommends \
	gcc \
	g++ \
	libffi-dev \
	libssl-dev \
	curl \
	&& rm -rf /var/lib/apt/lists/*

workdir /app

# install python dependencies first (layer caching)
copy requirements_dash.txt .
run pip install --no-cache-dir -r requirements_dash.txt && \
	pip install --no-cache-dir gunicorn==21.2.0

# copy application source
copy app.py .
copy snowflake_session.py .

# spcs expects the service to listen on port 8080
expose 8080

# health check: ensure the app is responding
healthcheck --interval=30s --timeout=10s --start-period=5s --retries=3 \
	cmd curl -f http://localhost:8080/ || exit 1

# gunicorn serves the dash app's underlying flask server.
# --workers 1 is recommended when using snowpark sessions (session is global).
# --timeout 120 is sufficient for complex snowflake queries.
cmd ["gunicorn", \
	"--bind", "0.0.0.0:8080", \
	"--workers", "1", \
	"--timeout", "120", \
	"--access-logfile", "-", \
	"--error-logfile", "-", \
	"app:server"]
