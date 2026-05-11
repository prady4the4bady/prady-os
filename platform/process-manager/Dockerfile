FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    xdotool wmctrl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY process_manager.py process_manager_router.py ./
CMD ["python", "-m", "uvicorn", "process_manager_router:router", "--host", "0.0.0.0", "--port", "8093"]
