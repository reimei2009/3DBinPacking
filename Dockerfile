# Reproducible container for the Streamlit research/demo UI.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Copy dependency metadata first so Docker can reuse this layer when only
# application code changes.
COPY pyproject.toml README.md ./
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install ".[web]"

COPY . .

# The application derives processed inputs from tracked raw data and creates
# immutable run directories at runtime. Both locations must be writable when
# the service runs as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/interim /app/data/processed /app/outputs \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8501

# Render provides PORT at runtime. The fallback keeps `docker run -p` useful
# for local verification.
CMD ["sh", "-c", "streamlit run src/container_packing/web/streamlit_app.py --server.address=0.0.0.0 --server.port=${PORT:-8501} --server.headless=true"]
