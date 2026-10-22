#!/usr/bin/env bash
# ==============================================================================
# Setup & Deployment Script untuk Kalodata Scraper & Dashboard di VPS (Ubuntu/Debian)
# ==============================================================================
set -euo pipefail

# 1. Pastikan dijalankan sebagai root / sudo
if [ "$EUID" -ne 0 ]; then
  echo "[ERROR] Script ini harus dijalankan dengan hak akses root (gunakan: sudo bash setup_vps.sh)"
  exit 1
fi

echo "================================================================="
echo "   Memulai Otomatisasi Instalasi & Persiapan VPS Kalodata Scraper"
echo "================================================================="

# 2. Deteksi direktori project
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Jika aplikasi dijalankan di luar /opt/kalodata, buat symlink atau gunakan APP_DIR
TARGET_DIR="/opt/kalodata"
if [ "$APP_DIR" != "$TARGET_DIR" ]; then
    echo "[INFO] Menyiapkan target direktori $TARGET_DIR..."
    mkdir -p /opt
    if [ ! -d "$TARGET_DIR" ]; then
        ln -s "$APP_DIR" "$TARGET_DIR"
    fi
fi

# 3. Update repositori sistem & pasang dependensi OS
echo "[1/7] Memperbarui paket sistem dan menginstal dependensi dasar..."
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    build-essential \
    libpq-dev \
    python3 \
    python3-pip \
    python3-venv \
    xvfb \
    x11vnc \
    fluxbox \
    ca-certificates

# 4. Pastikan Docker & Docker Compose terpasang
echo "[2/7] Memeriksa instalasi Docker & Docker Compose..."
if ! command -v docker &>/dev/null; then
    echo "[INFO] Menginstal Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm -f get-docker.sh
fi

if ! docker compose version &>/dev/null; then
    echo "[INFO] Menginstal Docker Compose plugin..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-plugin || true
fi

# 5. Siapkan Python Virtual Environment (venv)
echo "[3/7] Membuat Python Virtual Environment dan menginstal dependensi..."
if [ ! -d "$TARGET_DIR/venv" ]; then
    python3 -m venv "$TARGET_DIR/venv"
fi

"$TARGET_DIR/venv/bin/pip" install --upgrade pip setuptools wheel
"$TARGET_DIR/venv/bin/pip" install -e "$TARGET_DIR"

# 6. Pasang browser Playwright Chromium beserta lib pendukungnya di VPS
echo "[4/7] Mengunduh Chromium untuk Playwright & pustaka sistem..."
"$TARGET_DIR/venv/bin/playwright" install chromium
"$TARGET_DIR/venv/bin/playwright" install-deps chromium

# 7. Konfigurasi file .env
echo "[5/7] Mengonfigurasi file .env..."
if [ ! -f "$TARGET_DIR/.env" ]; then
    cp "$TARGET_DIR/.env.example" "$TARGET_DIR/.env"
    RANDOM_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|change-this-to-a-very-secure-random-string|$RANDOM_SECRET|g" "$TARGET_DIR/.env"
    echo "[INFO] File .env baru dibuat dengan SECRET_KEY yang aman."
fi

# Pastikan permission executable pada script deploy
chmod +x "$TARGET_DIR/deploy/start_vnc.sh" || true

# 8. Jalankan Database (PostgreSQL) & Redis via Docker
echo "[6/7] Menjalankan Database PostgreSQL & Redis via Docker..."
cd "$TARGET_DIR"
docker compose up -d kalodata-db kalodata-redis

echo "[INFO] Menunggu PostgreSQL dan Redis siap..."
sleep 5

# Inisialisasi struktur tabel database
echo "[INFO] Menginisialisasi schema tabel database..."
"$TARGET_DIR/venv/bin/python" -c "from app.models import init_db; init_db(); print('Database schema initialized!')"

# Buat admin user default jika belum ada
echo "[INFO] Memastikan akun admin default tersedia..."
"$TARGET_DIR/venv/bin/python" -m app.cli create-admin --username admin --password admin || true

# 9. Registrasi dan jalankan service systemd di Host VPS
echo "[7/7] Memasang dan mengaktifkan service systemd..."
cp "$TARGET_DIR/deploy/kalodata-vnc.service" /etc/systemd/system/
cp "$TARGET_DIR/deploy/kalodata-web.service" /etc/systemd/system/
cp "$TARGET_DIR/deploy/kalodata-worker.service" /etc/systemd/system/
cp "$TARGET_DIR/deploy/kalodata-beat.service" /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now kalodata-vnc
systemctl enable --now kalodata-web
systemctl enable --now kalodata-worker
systemctl enable --now kalodata-beat

echo ""
echo "================================================================="
echo "   SELAMAT! DEPLOYMENT KALODATA SCRAPER BERHASIL DIKONFIGURASI"
echo "================================================================="
IP_ADDR=$(hostname -I | awk '{print $1}' || echo "<IP-VPS>")
echo "1. Web Dashboard Scraper : http://$IP_ADDR:8081"
echo "   Akun Default          : admin / admin"
echo ""
echo "2. VNC Viewer (Display :1): $IP_ADDR:5901"
echo "   (Digunakan untuk login manual Kalodata jika sesi habis)"
echo ""
echo "3. Perintah Cek Status:"
echo "   sudo systemctl status kalodata-web"
echo "   sudo systemctl status kalodata-worker"
echo "   sudo systemctl status kalodata-vnc"
echo "   sudo systemctl status kalodata-beat"
echo ""
echo "4. Cek Log Worker Real-time:"
echo "   sudo journalctl -u kalodata-worker -f"
echo "================================================================="
