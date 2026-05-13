FROM python:3.12-slim AS builder
RUN apt-get update && apt-get install -y \
    build-essential gcc git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY inventor-engine/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim
RUN apt-get update && apt-get install -y \
    git docker.io curl \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1001 appuser && \
    usermod -aG docker appuser
COPY --from=builder /root/.local /home/appuser/.local
WORKDIR /app
COPY inventor-engine/ .
COPY shared/ /app/shared/
RUN mkdir -p /data/inventor /var/prady/projects && \
    chown -R appuser:appuser /data/inventor /var/prady/projects /app
USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app:/app/shared
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import httpx,sys; r=httpx.get('http://localhost:8022/health',timeout=5); sys.exit(0 if r.json().get('status')=='ok' else 1)"
CMD ["uvicorn", "inventor_service:app", "--host", "0.0.0.0", "--port", "8022"]
