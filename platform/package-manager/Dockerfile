FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY package_manager_service.py ./
COPY catalog/ ./catalog/

ENV DATA_DIR=/data
ENV CATALOG_DIR=/app/catalog
ENV PYTHONUNBUFFERED=1

EXPOSE 8116

CMD ["uvicorn", "package_manager_service:app", "--host", "0.0.0.0", "--port", "8116"]
