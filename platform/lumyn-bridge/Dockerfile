FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY lumyn_bridge.py ./lumyn_bridge.py

EXPOSE 8102

CMD ["uvicorn", "lumyn_bridge:app", "--host", "0.0.0.0", "--port", "8102"]
