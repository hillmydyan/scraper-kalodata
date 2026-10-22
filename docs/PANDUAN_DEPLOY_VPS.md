# Panduan Lengkap Deploy Kalodata Scraper & Dashboard di VPS

Dokumen ini berisi panduan langkah demi langkah untuk melakukan deploy aplikasi **Kalodata Web Scraper & Dashboard** ke server VPS (Virtual Private Server).

---

## 1. Spesifikasi Minimum VPS yang Disarankan

* **OS:** Ubuntu 22.04 LTS atau Ubuntu 24.04 LTS (x86_64)
* **CPU:** Minimal 2 vCPU (disarankan 4 vCPU agar proses browser Playwright lancar)
* **RAM:** Minimal 4 GB (Playwright Chromium + Docker Postgres & Redis membutuhkan memory yang cukup)
* **Disk:** Minimal 20 GB SSD
* **Port yang Perlu Dibuka di Firewall VPS (UFW / Security Group):**
  * `Port 22`: SSH
  * `Port 8081`: Dashboard Web Scraper (atau `Port 80/443` jika menggunakan Nginx & Domain)
  * `Port 5901`: VNC Server (Display `:1`) untuk login manual Kalodata

---

## 2. Cara Transfer Project ke VPS

Pilih salah satu cara di bawah ini untuk memindahkan folder project ke VPS:

### Opsi A: Menggunakan Git (Paling Disarankan)
Di terminal VPS:
```bash
git clone <URL_REPOSITORY_ANDA> /opt/kalodata
cd /opt/kalodata
```

### Opsi B: Menggunakan SCP / Rsync dari Komputer Lokal
Di terminal komputer lokal:
```bash
# Upload seluruh folder project ke VPS
scp -r c:/Users/User/Downloads/PROJECT/scraper-kalodata root@<IP_VPS>:/opt/kalodata
```

---

## 3. Instalasi Otomatis (1-Click Setup)

Kami telah menyediakan script otomatisasi lengkap di folder `deploy/`. Di terminal VPS:

```bash
cd /opt/kalodata
sudo bash deploy/setup_vps.sh
```

### Apa yang Dilakukan Script Ini Secara Otomatis?
1. Menginstal seluruh dependensi sistem Linux: `python3`, `python3-venv`, `libpq-dev`, `xvfb`, `x11vnc`, `fluxbox`, `docker`.
2. Menyiapkan Python Virtual Environment (`venv`) dan menginstal seluruh package Python.
3. Mengunduh browser Chromium resmi untuk Playwright beserta pustaka sistem pendukungnya.
4. Menjalankan container PostgreSQL 15 dan Redis 7 secara terisolasi via Docker Compose.
5. Menginisialisasi schema tabel database dan membuat akun admin dashboard pertama (`admin` / `admin`).
6. Memasang & mengaktifkan 4 background service systemd:
   * `kalodata-vnc.service`: Menjalankan virtual display & VNC server di port `5901`.
   * `kalodata-web.service`: Menjalankan web dashboard Gunicorn di port `8081`.
   * `kalodata-worker.service`: Menjalankan worker scraping Playwright.
   * `kalodata-beat.service`: Menjalankan penjadwal cron otomatis (jam 01.00 WIB).

---

## 4. Status Login Kalodata di VPS (Tanpa Perlu VNC!)

**KABAR BAIK: Anda TIDAK perlu login lewat VNC!**

Sesi login aktif dari laptop Anda sudah otomatis kami ekspor ke file:
[runtime/kalodata_session.json](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/runtime/kalodata_session.json)

Ketika Anda menyalin project ini ke VPS, file sesi tersebut ikut ter-upload. Engine scraper di VPS akan **secara otomatis menginjeksi cookies & token sesi ini** saat pertama kali browser berjalan, sehingga status akun langsung **READY** tanpa perlu login ulang atau membuka VNC.

### Cara Memastikan Sesi Sudah Aktif di VPS:
1. Buka browser: `http://<IP_VPS>:8081` (Akun: `admin` / `admin`).
2. Masuk ke menu **Akun & Sesi** (`/accounts`).
3. Klik tombol **"Validasi Sesi Browser"**.
4. Status akun akan langsung berubah menjadi **READY**.

---

### Kapan VNC Viewer (`Port 5901`) Dibutuhkan?
VNC **hanya berfungsi sebagai cadangan darurat (fallback)** jika:
* Di masa depan (misal berbulan-bulan kemudian) sesi Kalodata benar-benar kedaluwarsa, **DAN**
* Kalodata menampilkan puzzle/CAPTCHA interaktif Cloudflare Turnstile yang mengharuskan manusia mengklik centang.

Jika kondisi di atas tidak terjadi, Anda sama sekali tidak perlu mengunduh atau membuka VNC Viewer.

---

## 5. Pengujian Scraper (Smoke Test)

Untuk memastikan seluruh engine berjalan lancar di VPS, jalankan uji scraping manual:

### Cara 1: Lewat Web Dashboard
* Masuk ke menu **Jadwal & Job** (`/jobs`).
* Pada form manual trigger:
  * Pilih Negara: `Indonesia (ID)`
  * Modul: `Creator` atau `Product`
  * Limit: `5`
  * Klik tombol **"⚡ Jalankan Scraper Kalodata Sekarang"**.
* Perhatikan progres berjalan di tabel job.

### Cara 2: Lewat Terminal CLI di VPS
```bash
cd /opt/kalodata
source venv/bin/activate

# Uji struktur selektor UI
python -m app.cli smoke-selectors

# Jalankan scraping uji coba 5 item
python -m app.cli scrape --country ID --limit 5
```

---

## 6. Perintah Manajemen & Pemantauan (Cheat Sheet)

```bash
# 1. Cek status seluruh service scraper
sudo systemctl status kalodata-web
sudo systemctl status kalodata-worker
sudo systemctl status kalodata-vnc
sudo systemctl status kalodata-beat

# 2. Restart service jika ada perubahan konfigurasi
sudo systemctl restart kalodata-web
sudo systemctl restart kalodata-worker

# 3. Melihat log scraping real-time
sudo journalctl -u kalodata-worker -f

# 4. Melihat log web dashboard
sudo journalctl -u kalodata-web -f

# 5. Cek status database & redis di Docker
cd /opt/kalodata
docker compose ps
```

---

## 7. Setup Nginx Reverse Proxy & Domain SSL (Opsional)

Jika ingin mengakses dashboard lewat domain (mis. `kalodata.perusahaan.com`) dengan HTTPS:

```bash
# Salin konfigurasi nginx
sudo cp /opt/kalodata/deploy/nginx.conf /etc/nginx/sites-available/kalodata
# Ubah server_name di dalam file tersebut
sudo nano /etc/nginx/sites-available/kalodata

# Aktifkan site
sudo ln -s /etc/nginx/sites-available/kalodata /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Pasang SSL gratis via Certbot Let's Encrypt
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d kalodata.perusahaan.com
```
