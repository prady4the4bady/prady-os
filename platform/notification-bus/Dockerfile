FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app
WORKDIR /app

EXPOSE 8111
CMD ["uvicorn", "notification_service:app", "--host", "0.0.0.0", "--port", "8111"]
