FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json

RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]