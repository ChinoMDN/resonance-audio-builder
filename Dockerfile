# Base image
FROM python:3.11-slim

# Set environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Work directory
WORKDIR /app

# Install system dependencies (FFmpeg, Git)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Set permissions
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Default command
ENTRYPOINT ["python", "src/bypass_spotify.py"]
