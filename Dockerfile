# Use official Python image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    APP_HOME=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR $APP_HOME

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the application
CMD ["python", "main.py"]
