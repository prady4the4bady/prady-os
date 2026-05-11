FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    pciutils \
    dmidecode \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1
ENV PORT=8017
ENV DATA_DIR=/var/prady/bios-ai

EXPOSE 8017

CMD ["uvicorn", "bios_ai_service:app", "--host", "0.0.0.0", "--port", "8017"]
