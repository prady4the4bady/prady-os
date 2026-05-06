# syntax=docker/dockerfile:1
FROM python:3.12-slim

# ── System packages ──────────────────────────────────────────────────────────
# xdotool: mouse/keyboard automation via X11
# scrot: lightweight screenshot tool
# x11-apps, libx11-dev: X11 runtime support for python-xlib
RUN apt-get update && apt-get install -y --no-install-recommends \
        xdotool \
        scrot \
        x11-apps \
        libx11-dev \
        libxtst6 \
        libxi6 \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ──────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ─────────────────────────────────────────────────────────
COPY app/ ./app/

# ── Screenshot output directory ───────────────────────────────────────────────
RUN mkdir -p /tmp/screenshots && \
    useradd -m -u 1000 app && \
    chown -R app:app /tmp/screenshots && \
    chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
