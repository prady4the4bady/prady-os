FROM python:3.12-slim
RUN apt-get update && apt-get install -y sqlite3 && \
    rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data
CMD ["uvicorn", "persona_service:app", "--host", "0.0.0.0", "--port", "8114"]
