FROM python:3.11-slim-bookworm

# Install runtime dependencies: ffmpeg for audio processing, curl, gosu for user permissions
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    MUSICGETTER_CONFIG=/config/config.yaml \
    LIBRARY_DIR=/music \
    DATA_DIR=/config

ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "-m", "src.main"]
