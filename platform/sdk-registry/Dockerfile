FROM python:3.12-slim AS builder
RUN apt-get update && apt-get install -y \
    build-essential gcc && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim
RUN apt-get update && apt-get install -y \
    docker.io curl && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1001 appuser && \
    usermod -aG docker appuser
COPY --from=builder /root/.local /home/appuser/.local
WORKDIR /app
COPY . .
RUN mkdir -p /data/sdk_registry /home/user/prady-apps && \
    chown -R appuser:appuser /data/sdk_registry /home/user/prady-apps /app
USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import httpx; r=httpx.get('http://localhost:8020/health', timeout=5); exit(0 if r.json().get('status')=='ok' else 1)"
CMD ["uvicorn", "sdk_registry_service:app", "--host", "0.0.0.0", "--port", "8020"]
