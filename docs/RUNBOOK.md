# Runbook Operasional Kalodata Scraper Dashboard

Panduan operasional dan pemeliharaan sistem scraping Kalodata untuk tim Kurma Group.

---

## 1. Prosedur Login Ulang via VNC

Jika sesi login Kalodata habis (`LOGIN_REQUIRED`):

1. **Buka Dashboard**: Masuk ke menu **Akun & Sesi** (`http://<ip-vps>:8081/accounts`).
2. **Picukan Browser Login**:
   - Klik tombol **"Buka Browser Login (VNC)"** pada akun `default`.
   - Atau jalankan CLI di terminal VPS:
     ```bash
     python -m app.cli open-login --profile default
     ```
3. **Buka VNC Viewer**:
   - Sambungkan VNC Viewer Anda ke alamat IP VPS pada port `5901` (Display `:1`).
   - Browser Chromium Kalodata akan tampil di layar VNC.
4. **Login Manual**:
   - Masukkan kredensial akun Kalodata Anda secara manual pada form login Kalodata di VNC.
   - Selesaikan CAPTCHA/verifikasi jika diminta oleh Kalodata.
5. **Validasi Sesi**:
   - Setelah masuk ke dashboard Kalodata, kembali ke dashboard scraper dan klik tombol **"Validasi Sesi"**.
   - Sistem akan memverifikasi sesi dan mengubah status menjadi **READY**.

---

## 2. Melanjutkan Job yang Terhenti (Resume)

Jika job scraping terhenti karena timeout jaringan atau server reboot:

1. Data produk yang sudah di-scrape tersimpan secara otomatis di database melalui checkpoint per 25 baris.
2. Di dashboard, buka menu **Jadwal & Job** (`/jobs`), pilih job terkait, lalu klik **"Resume"**.
3. Sistem akan melanjutkan pengambilan data dari baris/halaman terakhir tanpa menghapus atau menduplikasi produk yang sudah tersimpan (idempotent upsert).

---

## 3. Ekspor Ulang File Excel

Jika file Excel hilang atau diperlukan pembaruan:

1. Buka menu **Hasil & Ekspor** (`/results`).
2. Temukan baris job yang diinginkan, lalu klik tombol **"🔄 Ekspor Ulang"**.
3. Sistem akan membaca ulang seluruh baris dari database PostgreSQL dan membuat file Excel baru dengan sufiks versi berikutnya (mis. `_v2.xlsx`) tanpa menimpa file lama.

---

## 4. Memperbarui Selector UI Kalodata

Jika Kalodata memperbarui antarmukanya dan terjadi error `SELECTOR_CHANGED`:

1. **JANGAN ubah kode Python**. Semua selector berada di file:
   [config/selectors.yaml](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/config/selectors.yaml).
2. Periksa screenshot diagnostik kegagalan di folder `runtime/screenshots/` atau via dashboard detail job.
3. Buka Kalodata di browser VNC, inspect elemen target, dan tambahkan selector baru ke daftar `fallbacks` atau ubah `primary`.
4. Uji keabsahan struktur selector dengan menjalankan:
   ```bash
   python -m app.cli smoke-selectors
   ```

---

## 5. Prosedur Restore Setelah VPS Reboot

Semua container Docker disetel dengan `restart: unless-stopped` dan worker systemd disetel dengan `Restart=always`:

1. **Periksa status container Docker**:
   ```bash
   docker compose ps
   ```
   Pastikan `kalodata-db`, `kalodata-redis`, `kalodata-web`, dan `kalodata-beat` berstatus Up / Healthy.
2. **Periksa status Celery worker di host**:
   ```bash
   sudo systemctl status kalodata-worker
   ```
3. **Periksa VNC Display**:
   Pastikan VNC server pada port `5901` (`:1`) aktif.
4. **Validasi kesehatan sistem**:
   Akses `http://127.0.0.1:8081/health` untuk memastikan database, Redis, dan penyimpanan dalam keadaan sehat.
