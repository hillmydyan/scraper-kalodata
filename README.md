# Kalodata Web Scraper & Dashboard (v2.0)

Aplikasi internal Kurma Group Indonesia untuk mengotomatisasi scraping produk Kalodata (kalodata.com) pada kategori **Bawahan Wanita** untuk tiga negara (**Indonesia, Malaysia, Thailand**), menyimpan riwayat ke PostgreSQL, dan menghasilkan file Excel harian terpisah.

---

## Arsitektur Singkat

- **Web Dashboard**: Flask 3 + Jinja2 + Flask-Login (Port `8081`)
- **Database**: PostgreSQL 15 (Docker Port `5433` di host)
- **Antrean & Scheduler**: Redis 7 (Docker Port `6380`) + Celery Beat (Jadwal 01.00 WIB)
- **Scraper Worker**: Celery Worker di host VPS dengan Playwright Chromium headful pada `DISPLAY=:1` (Port VNC `5901`)

---

## Langkah Setup Cepat di VPS

Untuk panduan lengkap langkah-demi-langkah, silakan baca [PANDUAN_DEPLOY_VPS.md](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/docs/PANDUAN_DEPLOY_VPS.md).

### 1-Click Automated Setup (Ubuntu/Debian)
Cukup jalankan script instalasi otomatis di direktori project pada VPS:
```bash
sudo bash deploy/setup_vps.sh
```
Script ini akan otomatis menginstal seluruh dependensi sistem (Docker, Python venv, Playwright Chromium, Xvfb, x11vnc), menjalankan database PostgreSQL & Redis, menginisialisasi tabel, dan mengaktifkan 4 service systemd otomatis.

### Akses Dashboard & VNC:
- **Web Dashboard:** `http://<IP-VPS>:8081` (Akun: `admin` / `admin`)
- **VNC Viewer (Login Kalodata):** `<IP-VPS>:5901`

---

## Perintah CLI Mandiri

Scraper dapat dijalankan secara mandiri langsung dari CLI tanpa membuka dashboard:

```bash
# Smoke test seluruh selector
python -m app.cli smoke-selectors

# Buka jendela login di VNC untuk profil browser persisten
python -m app.cli open-login --profile default

# Validasi sesi login
python -m app.cli validate-session --profile default

# Jalankan scraping (mis. Indonesia, batas 5 produk untuk testing)
python -m app.cli scrape --country ID --period yesterday --limit 5

# Ekspor ulang hasil job ke Excel
python -m app.cli export --job-id <JOB_UUID>
```

---

## Dokumentasi Lengkap
- [PRD Dokumen](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/PRD_Kalodata_Web_Scraper_Dashboard_v2%20(1).md)
- [Runbook Operasional](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/docs/RUNBOOK.md)
- [Laporan Audit Tahap 1](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/docs/REPORT_TAHAP_1.md)
- [Laporan PoC Tahap 2](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/docs/REPORT_TAHAP_2.md)
