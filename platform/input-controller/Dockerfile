FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    xdotool wmctrl xvfb \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY input_controller.py .
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8092"]
