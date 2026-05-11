FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY vyrex_proxy.py .

EXPOSE 8105
CMD ["uvicorn", "vyrex_proxy:app", "--host", "0.0.0.0", "--port", "8105"]
