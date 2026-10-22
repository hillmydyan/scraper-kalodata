FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Install Playwright Chromium and system dependencies
RUN playwright install --with-deps chromium

# Copy application files
COPY app/ ./app/
COPY config/ ./config/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8081

CMD ["gunicorn", "--bind", "0.0.0.0:8081", "--workers", "2", "app:create_app()"]
