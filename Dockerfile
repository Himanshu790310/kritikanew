FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PYTHONIOENCODING=UTF-8

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev

WORKDIR /app
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "120", "--worker-class", "uvicorn.workers.UvicornWorker", "main:app"]
