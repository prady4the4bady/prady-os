FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1
ENV PORT=8018
ENV DATA_DIR=/data

EXPOSE 8018

CMD ["uvicorn", "self_learning_service:app", "--host", "0.0.0.0", "--port", "8018"]
