FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Survive slow/flaky builder networks (files.pythonhosted.org timeouts)
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first (better Docker layer caching).
# --retries + long timeout: transient PyPI read timeouts no longer fail the build.
# --prefer-binary: always take wheels, never fall back to slow source builds.
COPY requirements.txt requirements-web.txt ./

# Set INSTALL_WEB=true to ship the optional web dashboard (FastAPI) too.
ARG INSTALL_WEB=false
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir \
       --retries 5 --timeout 120 --prefer-binary \
       -r requirements.txt \
    && if [ "$INSTALL_WEB" = "true" ]; then \
         pip install --no-cache-dir --retries 5 --timeout 120 --prefer-binary \
           -r requirements-web.txt; \
       fi

# Copy application code and bundled assets (start banner image)
COPY bot ./bot
COPY assets ./assets

# Non-root user + writable data directory for the SQLite database
RUN mkdir -p /app/data \
    && useradd --create-home appuser \
    && chown -R appuser:appuser /app

USER appuser

# Render / getvoroa health check (served by bot/health.py). The optional web
# dashboard uses the SAME port (PORT) - a service must listen on exactly one
# port, otherwise Voroa aborts the deployment.
EXPOSE 8080

CMD ["python", "-m", "bot.main"]
