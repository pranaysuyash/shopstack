# ── Builder stage ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1

RUN pip install --no-cache-dir uv

WORKDIR /app
# Only copy files that exist — pyproject.toml is not used (project uses setup.py)
COPY setup.py requirements.txt ./
COPY shopstack/ shopstack/

# Install the package and all dependencies (no dev extras)
RUN uv pip install --system --no-cache -e ".[cloud]"

# ── Runtime stage ─────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME="0.0.0.0" \
    GRADIO_SERVER_PORT=7860 \
    SHOPSTACK_DB_PATH="/app/data/shopstack.db" \
    SHOPSTACK_DATA_DIR="/app/data"

# Install runtime system deps (pyzbar for barcode scanning, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libzbar0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/shopstack /app/shopstack

# Copy app entry point and data directory structure
COPY app.py .
COPY data/ data/

# Create non-root user for security
RUN adduser --system --no-create-home shopstack && \
    mkdir -p /app/data && \
    chown shopstack:shopstack /app/data
USER shopstack

# Default: run with mock providers (no cloud/AI dependencies)
# Override via environment variables for production use.
ENV SHOPSTACK_OFF_THE_GRID=true

EXPOSE 7860

# Health check — Gradio exposes /healthz on newer versions
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860')" || exit 1

ENTRYPOINT ["python", "app.py"]
CMD ["--port", "7860"]

# ── Dev stage ─────────────────────────────────────────────────────────
# docker build --target dev -t shopstack:dev .
# docker run -p 7860:7860 -v $(pwd):/app shopstack:dev
FROM python:3.12-slim AS dev

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME="0.0.0.0" \
    GRADIO_SERVER_PORT=7860 \
    SHOPSTACK_DB_PATH="/app/data/shopstack.db" \
    SHOPSTACK_DATA_DIR="/app/data"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libzbar0 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app

# Install all deps (including dev/test) for local iteration
COPY setup.py requirements.txt ./
RUN uv pip install --system --no-cache -e ".[dev]"

COPY app.py ./
COPY data/ data/
COPY shopstack/ shopstack/
COPY tests/ tests/
COPY benchmarks/ benchmarks/

RUN adduser --system --no-create-home shopstack && \
    mkdir -p /app/data && \
    chown shopstack:shopstack /app/data
USER shopstack

EXPOSE 7860

CMD ["python", "app.py", "--port", "7860"]
