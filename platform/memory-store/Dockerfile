FROM python:3.12-slim
WORKDIR /app
RUN mkdir -p /app/data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY memory_store.py memory_store_router.py ./
CMD ["python", "-m", "uvicorn", "memory_store_router:router", "--host", "0.0.0.0", "--port", "8094"]
