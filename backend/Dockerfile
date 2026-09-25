# Use official lightweight Python image
FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app/ ./app/

# Expose default port
EXPOSE 8000

# Use exec to allow graceful termination signals in containers
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
