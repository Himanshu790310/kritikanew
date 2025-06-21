FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    TELEGRAM_BOT_TOKEN=7833059587:AAGWCrFoYJqaIy51BHHRVtNrimJbZGTMows \
    GOOGLE_API_KEY=AIzaSyDc6wrTkV2k4AWl72NZxET6URrXCbM8haM \
    WEBHOOK_URL=https://kritikanew1-494584189423.europe-west1.run.app/webhook

WORKDIR /app
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "--worker-class", "uvicorn.workers.UvicornWorker", "main:app"]
