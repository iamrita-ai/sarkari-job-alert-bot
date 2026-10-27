FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot ./bot

# Non-root user + writable data directory for the SQLite database
RUN mkdir -p /app/data \
    && useradd --create-home appuser \
    && chown -R appuser:appuser /app

USER appuser

# Render / getvoroa health check (served by bot/health.py)
EXPOSE 8080

CMD ["python", "-m", "bot.main"]
