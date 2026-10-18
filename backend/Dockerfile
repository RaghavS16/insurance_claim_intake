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

# Install Python dependencies
COPY requirements.lock requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.lock \
    && python -m nltk.downloader -d /usr/local/share/nltk_data punkt_tab \
    && apt-get purge -y --auto-remove gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the rest of the application
COPY . .
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NLTK_DATA=/usr/local/share/nltk_data ENVIRONMENT=production DEBUG=false

# Create a non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
RUN chown -R appuser:appgroup /app \
    && chmod -R go-rwx /app
USER appuser

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

# Run the FastAPI server
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
