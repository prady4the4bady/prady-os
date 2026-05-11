FROM python:3.12-slim

WORKDIR /app

# System deps for process management
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY platform/agent-runtime/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy runtime source
COPY platform/agent-runtime/agent_api.py ./agent_api.py
COPY vyrex/runtime /app/vyrex/runtime/
COPY vyrex/policies /app/vyrex/policies/
RUN touch /app/vyrex/__init__.py /app/vyrex/runtime/__init__.py

EXPOSE 8100

CMD ["uvicorn", "agent_api:app", "--host", "0.0.0.0", "--port", "8100"]
