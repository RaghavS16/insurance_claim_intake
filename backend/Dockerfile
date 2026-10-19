FROM python:3.11-slim

WORKDIR /app

# Install system-level dependencies for psycopg2 and audio libs
RUN apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    ffmpeg \
    libopus0 \
    libsrtp2-1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from exact lockfile
COPY requirements.lock requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.lock \
    && apt-get purge -y --auto-remove gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Environment variables pointing to pre-downloaded baked model paths
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    DEBUG=false \
    FASTEMBED_CACHE_DIR=/opt/models/fastembed \
    HF_HOME=/opt/models/huggingface \
    NLTK_DATA=/opt/models/nltk_data

# Bake models into the image at build time under /opt/models
RUN mkdir -p /opt/models/fastembed /opt/models/huggingface /opt/models/nltk_data \
    && python -m nltk.downloader -d /opt/models/nltk_data punkt_tab punkt \
    && python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-base-en-v1.5', cache_dir='/opt/models/fastembed')" \
    && python -c "from faster_whisper import WhisperModel; WhisperModel('Systran/faster-distil-whisper-medium.en', download_root='/opt/models/huggingface')"

# Copy application source code
COPY . .

# Create a non-root user and assign ownership of app and model directories
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser \
    && chown -R appuser:appgroup /app /opt/models \
    && chmod -R go-rwx /app
USER appuser

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

# Run migrations and start FastAPI server with proxy headers and forwarded IPs
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1}"]

