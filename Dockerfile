# Base image resmi Playwright dari Microsoft (Ubuntu Jammy)
# Mencakup seluruh pustaka native Linux, GTK, X11, dan font Asia Tenggara
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Jakarta

# Install dependensi tambahan untuk Database & VNC Server
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    build-essential \
    libpq-dev \
    curl \
    xvfb \
    x11vnc \
    fluxbox \
    procps \
    x11-xserver-utils \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Verifikasi browser Playwright Chromium & Google Chrome resmi
RUN playwright install chromium
RUN playwright install --with-deps chrome || true

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
