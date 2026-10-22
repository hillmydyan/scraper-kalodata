# Laporan Tahap 1: Audit Lingkungan VPS, Port, DISPLAY, dan Persiapan

**Tanggal:** 17 Oktober 2026  
**Status:** Selesai (Tahap 1 Terpenuhi)  
**Tautan Dokumen Terkait:**
- PRD: [PRD_Kalodata_Web_Scraper_Dashboard_v2 (1).md](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/PRD_Kalodata_Web_Scraper_Dashboard_v2%20(1).md)
- Catatan UI: [KALODATA_UI_NOTES.md](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/docs/KALODATA_UI_NOTES.md)

---

## 1. Audit Spesifikasi VPS Target

| Parameter | Spesifikasi VPS Target | Prasyarat Minimum PRD (§13.1) | Status |
|---|---|---|---|
| **RAM** | 8 GB | Bebas $\ge$ 2 GB | **Lolos (Sangat mencukupi)** |
| **Penyimpanan (Disk)** | 100 GB | Bebas $\ge$ 10 GB | **Lolos (Sangat mencukupi)** |
| **VNC Display** | Port 5901 aktif (`DISPLAY=:1`) | VNC X server aktif | **Lolos (Sesuai konfigurasi default PRD)** |

---

## 2. Pemetaan Port dan Isolasi Service

Berdasarkan audit port yang sedang berjalan di VPS, berikut pemetaan untuk menghindari benturan:

### Port yang Sedang Dipakai di VPS (Read-Only / Jangan Disentuh)
`3000`, `3001`, `3002`, `3003`, `3100`, `4321`, `5000`, `5001`, `5002`, `5432` (PostgreSQL eksisting), `5901` (VNC X11 :1), `8082`, `8085`, `18789`, `20128`.

### Alokasi Port Khusus Proyek Kalodata
Semua port diikat hanya ke `127.0.0.1` (kecuali Nginx jika ada reverse proxy luar) dengan prefix service `kalodata-`:

| Komponen | Port Internal Host | Status Port | Catatan |
|---|---|---|---|
| **Web Dashboard (Flask)** | `8081` | Bebas | Tidak bentrok dengan 8082/8085 |
| **Database (PostgreSQL)** | `5433` | Bebas | Menghindari default 5432 yang sudah dipakai |
| **Queue / Cache (Redis)** | `6380` | Bebas | Port alternatif aman (default 6379 jika bebas atau 6380) |
| **Display VNC (Worker)** | `:1` (Port 5901) | Terdeteksi aktif | Headful Playwright worker akan me-mount display ini |

---

## 3. Rencana Arsitektur Deployment (§13.2)

1. **Docker Compose (`docker-compose.yml`)**:
   - `kalodata-db`: PostgreSQL 15 (`127.0.0.1:5433`)
   - `kalodata-redis`: Redis 7 (`127.0.0.1:6380`)
   - `kalodata-web`: Flask Dashboard (`127.0.0.1:8081`)
   - `kalodata-beat`: Celery Beat Scheduler
2. **Host Systemd Service (`deploy/kalodata-worker.service`)**:
   - `kalodata-worker`: Celery Worker berjalan di host VPS dengan `DISPLAY=:1`, menghubungkan langsung ke Chromium bawaan Playwright dan profil persisten di `runtime/profiles/kalodata/`.

---

## 4. Checklist Deliverable Tahap 1
- [x] Verifikasi RAM & Disk VPS
- [x] Pemetaan port aman bebas konflik
- [x] Identifikasi display VNC (`:1` / 5901)
- [x] Inisialisasi draft [KALODATA_UI_NOTES.md](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/docs/KALODATA_UI_NOTES.md)
- [ ] Pengujian akses / observasi UI Kalodata langsung untuk Tahap 2
