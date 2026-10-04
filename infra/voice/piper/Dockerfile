FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

RUN pip install --no-cache-dir "piper-tts[http]==1.7.0"

EXPOSE 5001

USER 65532:65532

CMD ["python", "-m", "piper.http_server", "-m", "en_US-ryan-high", "--host", "0.0.0.0", "--port", "5001"]
