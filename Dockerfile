# syntax=docker/dockerfile:1.7

################################################################################
# STAGE 1: Builder
# - Installs system dependencies
# - Downloads and wheels Python packages
################################################################################
FROM python:3.11-slim AS builder

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies
# build-essential is needed for packages that compile C extensions.
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip
RUN pip wheel --wheel-dir /wheels -r requirements.txt


################################################################################
# STAGE 2: Runtime
# - Creates a slim, production-ready image
# - Uses a non-root user
################################################################################
FROM python:3.11-slim AS runtime

# Set image metadata
LABEL org.opencontainers.image.source="https://github.com/naeemAbdul-Aziz/complimate-ai-engine" \
      org.opencontainers.image.title="CompliMate AI Engine" \
      org.opencontainers.image.description="Contract compliance analysis engine" \
      org.opencontainers.image.license="Proprietary" \
      org.opencontainers.image.version="2.0.2"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    ENABLE_WEBSOCKETS=True

WORKDIR /app

# Create a non-root user and group
RUN addgroup --system app && adduser --system --ingroup app app

# Install Python dependencies from the builder's wheel cache
COPY --from=builder /wheels /wheels
COPY requirements.txt ./
RUN pip install --no-index --find-links /wheels -r requirements.txt && \
    rm -rf /wheels

# Copy only the necessary application source code
COPY api ./api
COPY engine ./engine
COPY config ./config
COPY reporting ./reporting
COPY utils ./utils
COPY tasks ./tasks

# Create and set permissions for runtime directories
# These directories will be used for logs, uploads, reports, and the vector store
RUN mkdir -p logs uploads reports vector_store && \
    chown -R app:app /app

# Switch to the non-root user
USER app

# Expose the port the app runs on
EXPOSE 8000

# Healthcheck to verify the API is responsive
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request, sys; \
        try: \
                r = urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3); \
                sys.exit(0 if r.status == 200 else 1); \
        except Exception: \
                sys.exit(1)"

# Entrypoint command to run the Uvicorn server
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]