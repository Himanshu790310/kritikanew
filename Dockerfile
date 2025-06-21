FROM python:3.11-slim

# Set critical environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PYTHONIOENCODING=UTF-8 \
    GUNICORN_CMD_ARGS="--workers=1 --threads=4 --timeout=120 --worker-class=uvicorn.workers.UvicornWorker"

# Install system dependencies + clean cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Install Python dependencies with precise versions
RUN pip install --no-cache-dir -r requirements.txt

# Run with optimized Gunicorn
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:8080"]
