# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim
LABEL maintainer="CIMAPRA"

# Non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .

RUN mkdir -p instance && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Gunicorn: production WSGI server
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "4", \
     "--worker-class", "sync", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
