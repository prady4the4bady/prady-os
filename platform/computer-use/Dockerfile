FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr xdotool ydotool libx11-dev scrot \
    libxtst-dev libpng-dev libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
WORKDIR /app
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "computer_use_service:app", "--host", "0.0.0.0", "--port", "8106"]
