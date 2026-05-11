FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

CMD ["uvicorn", "security_policy_service:app", "--host", "0.0.0.0", "--port", "8117"]
