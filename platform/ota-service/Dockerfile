FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    bsdiff \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

ENV MANIFEST_URL=http://localhost:8012/static/manifest.json
ENV SLOT_DB_PATH=/data/ota/slot_state.db
ENV STAGING_DIR=/data/ota/staging
ENV GRUBENV_PATH=/tmp/grubenv

EXPOSE 8012

CMD ["uvicorn", "ota_service:app", "--host", "0.0.0.0", "--port", "8012"]
