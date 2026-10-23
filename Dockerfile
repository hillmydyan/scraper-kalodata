FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including Xvfb, fluxbox, x11vnc for container VNC
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    xvfb \
    x11vnc \
    fluxbox \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Install Playwright Chromium and its system dependencies
RUN playwright install --with-deps chromium

# Copy application files and deploy scripts
COPY app/ ./app/
COPY config/ ./config/
COPY deploy/ ./deploy/
COPY run.py .

# Ensure entrypoints are executable
RUN chmod +x deploy/*.sh

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8081 5901 5902

CMD ["gunicorn", "--bind", "0.0.0.0:8081", "--workers", "2", "app:create_app()"]
