FROM python:3.11-slim

# Install system dependencies for snowflake-snowpark-python
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements_dash.txt .
RUN pip install --no-cache-dir -r requirements_dash.txt

# Copy application source
COPY app.py .
COPY snowflake_session.py .

# SPCS expects the service to listen on port 8080
EXPOSE 8080

# Gunicorn serves the Dash app's underlying Flask server.
# --workers 1 is recommended when using Snowpark sessions (session is global).
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120", "app:server"]
