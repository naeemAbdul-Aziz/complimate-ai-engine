# syntax=docker/dockerfile:1.7
############################################
# Builder Stage
############################################
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (add poppler/other libs if needed for advanced PDF later)
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip wheel --wheel-dir /wheels -r requirements.txt

############################################
# Runtime Stage
############################################
FROM python:3.11-slim AS runtime
LABEL org.opencontainers.image.source="https://github.com/naeemAbdul-Aziz/complimate-ai-engine" \
      org.opencontainers.image.title="CompliMate AI Engine" \
      org.opencontainers.image.description="Contract compliance analysis engine" \
      org.opencontainers.image.license="Proprietary" \
      org.opencontainers.image.version="2.0.2"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    ENABLE_WEBSOCKETS=True

WORKDIR /app

# Non-root user
RUN addgroup --system app && adduser --system --ingroup app app

# Copy wheels & install
COPY --from=builder /wheels /wheels
COPY requirements.txt ./
RUN pip install --no-index --find-links /wheels -r requirements.txt && rm -rf /wheels

# Copy source
COPY api ./api
COPY engine ./engine
COPY config ./config
COPY reporting ./reporting
COPY data ./data
COPY utils ./utils
COPY scripts ./scripts
COPY main.py ./main.py
COPY api.py ./api.py
COPY docs ./docs

# Create runtime dirs
RUN mkdir -p logs uploads reports vector_store && chown -R app:app /app

USER app

EXPOSE 8000

# Healthcheck (basic) - lightweight HTTP probe
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys;\n\
import json;\n\
try:\n\
    r=urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3);\n\
    sys.exit(0 if r.status==200 else 1)\n\
except Exception: sys.exit(1)" || exit 1

# Entrypoint
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
