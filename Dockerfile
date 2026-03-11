FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Reinstall playwright browsers inside the pip environment
RUN python -m playwright install chromium

COPY . .

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}