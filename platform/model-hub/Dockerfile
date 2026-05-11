FROM python:3.12-slim
RUN apt-get update && apt-get install -y curl git && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
ENV PYTHONUNBUFFERED=1
EXPOSE 8113
CMD ["uvicorn", "model_hub_service:app", "--host", "0.0.0.0", "--port", "8113"]
