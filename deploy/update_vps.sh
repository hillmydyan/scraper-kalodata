#!/usr/bin/env bash
# ==============================================================================
# Script Update Otomatis & Restart Worker di VPS
# Menjamin kode terbaru langsung aktif di background worker & web dashboard
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "================================================================="
echo "   Memulai Update Kalodata Scraper & Dashboard di VPS"
echo "================================================================="

cd "$APP_DIR"

echo "[1/3] Menarik kode pembaruan terbaru dari Git..."
git pull origin main

# Jika ada systemd services
if systemctl list-unit-files | grep -q "kalodata-worker"; then
    echo "[2/3] Memuat ulang service systemd..."
    sudo systemctl daemon-reload
    echo "       -> Restart kalodata-worker..."
    sudo systemctl restart kalodata-worker
    echo "       -> Restart kalodata-web..."
    sudo systemctl restart kalodata-web
    echo "       -> Restart kalodata-beat..."
    sudo systemctl restart kalodata-beat
fi

# Jika menggunakan Docker Compose untuk web/worker
if command -v docker &>/dev/null && [ -f "$APP_DIR/docker-compose.yml" ]; then
    if docker compose ps | grep -q "kalodata-worker"; then
        echo "[2/3-docker] Membangun ulang dan restart container Docker..."
        docker compose up -d --build kalodata-web kalodata-worker kalodata-beat
    fi
fi

echo "[3/3] Memeriksa status service worker..."
if systemctl list-unit-files | grep -q "kalodata-worker"; then
    sudo systemctl --no-pager status kalodata-worker | head -n 12
fi

echo ""
echo "================================================================="
echo "   PEMBARUAN SELESAI & WORKER SUDAH BERJALAN DENGAN KODE TERBARU!"
echo "================================================================="
