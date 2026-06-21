FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default to offline mode; override with real provider + key at runtime.
ENV LLM_PROVIDER=mock

# Hugging Face Spaces expects 7860; other hosts inject $PORT.
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-7860}"]
