FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpam0g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1
ENV AUTH_DB_PATH=/data/auth.db
ENV JWT_PRIVATE_KEY_PATH=/run/secrets/prady-jwt-private.pem
ENV JWT_PUBLIC_KEY_PATH=/run/secrets/prady-jwt-public.pem

EXPOSE 8013
CMD ["uvicorn", "auth_service:app", "--host", "0.0.0.0", "--port", "8013"]
