FROM python:3.12-slim

# Install FFmpeg with full codec support (libx264, aac, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libx264-dev \
        libavcodec-extra \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Create storage directories (ephemeral on Render free tier)
RUN mkdir -p storage/original storage/processed storage/analysis

CMD ["python", "mcp_server.py"]
