FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY audit_log_service.py ./

EXPOSE 8112

CMD ["uvicorn", "audit_log_service:app", "--host", "0.0.0.0", "--port", "8112"]
