# Indian Stock Analyzer: one image with the FastAPI server and the built React frontend.
# Used by Cloudflare Containers (wrangler.jsonc) and works on any Docker host.
#
#   docker build -t stock-analyzer .
#   docker run -p 8000:8000 stock-analyzer

# ---------- 1. build the frontend ----------
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2. runtime ----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    ISA_ENABLE_PORTFOLIO=false
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
COPY --from=web /web/dist ./frontend/dist

# Run as an unprivileged user; it owns only the folders the app writes to.
RUN useradd --create-home --uid 10001 app \
 && mkdir -p cache logs output data \
 && chown -R app:app cache logs output data
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health', timeout=4)"

# One worker: the price-alert thread and the in-memory caches live in this process.
CMD ["sh", "-c", "exec uvicorn server.app:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
