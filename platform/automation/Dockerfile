FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ydotool \
    scrot \
    xdotool \
    && rm -rf /var/lib/apt/lists/*

COPY platform/automation/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY platform/automation/automation_service.py ./automation_service.py
COPY vyrex/policies /app/vyrex/policies/

ENV DISPLAY=:0
ENV WAYLAND_DISPLAY=wayland-0

EXPOSE 8101

CMD ["uvicorn", "automation_service:app", "--host", "0.0.0.0", "--port", "8101"]
