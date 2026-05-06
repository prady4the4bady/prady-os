FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY config/ ./config/
RUN mkdir -p /app/data/chroma && \
	useradd -m -u 1000 app && \
	chown -R app:app /app

USER app

EXPOSE 11436

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "11436"]
