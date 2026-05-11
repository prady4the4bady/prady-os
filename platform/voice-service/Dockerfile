FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    ffmpeg libsndfile1 portaudio19-dev \
    wget curl && rm -rf /var/lib/apt/lists/* && \
    wget -q https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz \
    -O /tmp/piper.tar.gz && \
    mkdir -p /root/.prady/bin && \
    tar -xf /tmp/piper.tar.gz -C /root/.prady/bin/ && \
    rm /tmp/piper.tar.gz && \
    chmod +x /root/.prady/bin/piper

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "voice_service:app", "--host", "0.0.0.0", "--port", "8012"]
