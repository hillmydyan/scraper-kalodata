# Product Requirements Document (PRD)

# Kalodata Web Scraper Dashboard

**Versi:** 2.0
**Tanggal:** 17 Oktober 2026
**Status:** Siap untuk development (PoC dulu, lihat §24)
**Pemilik produk:** Kurma Group Indonesia
**Zona waktu operasional:** Asia/Jakarta (WIB, UTC+7)
**Target deployment:** Ubuntu VPS yang sudah memiliki VNC dan scraper lain
**Teknologi utama:** Python 3.11+, Playwright, Flask, PostgreSQL, Redis, Celery, Docker Compose

### Riwayat perubahan

| Versi | Tanggal | Perubahan |
|---|---|---|
| 1.0 | — | Draft awal |
| 1.1 | 17 Okt 2026 | Cakupan ditetapkan: Kalodata saja |
| 2.0 | 17 Okt 2026 | Pertanyaan terbuka diubah jadi keputusan default; ditambah: panduan agent, arsitektur proses, konfigurasi, selector eksternal, parsing angka per negara, aturan video, state machine job, API, env, testing, retensi, readiness data, batasan pengaksesan |

---

## 0. Panduan untuk Agent Developer (BACA DULU)

Bagian ini mengatur cara agent bekerja agar tidak salah arah.

### 0.1 Prinsip kerja

1. **PoC sebelum arsitektur.** Jangan membangun dashboard, Celery, atau Docker sebelum Tahap 2 (PoC satu produk) lolos dan hasilnya dilaporkan ke pemilik produk.
2. **Jangan menebak UI Kalodata.** Semua label filter, nama kategori, selector, dan format angka WAJIB diverifikasi di browser nyata pada Tahap 1–2, lalu dicatat di `config/selectors.yaml` dan `docs/KALODATA_UI_NOTES.md`. Nilai yang tertulis di PRD ini adalah *ekspektasi*, bukan fakta yang sudah diverifikasi, kecuali ditandai **[TERVERIFIKASI]**.
3. **Keputusan default sudah ditetapkan di §19.** Agent memakai default itu tanpa bertanya lagi. Agent hanya berhenti dan bertanya jika menemukan kondisi di §0.3.
4. **Jangan sentuh yang sudah ada di VPS.** Scraper lain, profil browser lain, service lain, konfigurasi VNC yang ada — read-only. Semua resource proyek ini memakai prefix `kalodata-` (nama container, service, direktori, user DB).
5. **Setiap tahap punya deliverable yang bisa dicek** (§17). Tahap berikutnya tidak dimulai sebelum deliverable tahap sebelumnya ada.
6. **Kode harus bisa dijalankan tanpa dashboard.** Scraper harus bisa dipanggil dari CLI (`python -m app.cli scrape --country ID --period yesterday`) sejak Tahap 2. Dashboard hanya membungkus CLI ini.
7. **Tidak ada hardcode.** Selector, label filter, nama kategori, URL, jadwal, retensi, batas halaman — semuanya di konfigurasi, bukan di kode Python.
8. **Jangan mengakali keamanan platform.** Jika menemukan CAPTCHA, Cloudflare challenge, OTP, atau pembatasan akses: hentikan job, set status yang sesuai, simpan screenshot, laporkan. Jangan mencari cara menembusnya.

### 0.2 Hal yang DILARANG

- Memakai endpoint API internal/XHR Kalodata secara langsung sebagai sumber data utama (boleh dicatat sebagai temuan, tidak boleh dipakai tanpa persetujuan tertulis).
- Menjalankan lebih dari satu browser context per profil secara paralel.
- Menjalankan job negara secara paralel pada profil yang sama.
- Menyimpan password, cookie, token, atau storage state di log, DB, atau UI.
- Mengubah file `.env` produksi; hanya `.env.example` yang boleh di-commit.
- Men-commit isi `runtime/`.
- Membuat file Excel yang isinya hasil parsial tanpa menandai status `PARTIAL` di nama file dan metadata.
- Mengisi kolom kosong dengan nilai tebakan (0, "-", "N/A"). Kosong tetap kosong (`NULL`).

### 0.3 Kapan agent harus berhenti dan bertanya

- Kalodata ternyata memerlukan akun berbeda per negara **dan** pemilik produk belum memberi akun kedua.
- Kategori yang setara dengan "Bawahan Wanita" tidak ditemukan atau ada lebih dari satu kandidat.
- Filter "sumber pendapatan = Video" tidak ada di halaman Product (lihat fallback §6.4 dulu sebelum bertanya).
- Data "kemarin" belum tersedia di Kalodata pada pukul 01.00 WIB (lihat §8.4).
- Jumlah produk per negara per hari > 2.000 (di luar asumsi kapasitas).
- VPS tidak memenuhi §13.1 (RAM/disk/versi).
- Kalodata menampilkan peringatan batas penggunaan/quota atau memblokir akun.

### 0.4 Format laporan agent per tahap

Setiap selesai tahap, agent menulis `docs/REPORT_TAHAP_N.md` berisi: apa yang dikerjakan, apa yang terverifikasi, apa yang berbeda dari PRD, keputusan yang diambil, screenshot bukti, dan daftar pertanyaan (jika ada).

---

## 1. Ringkasan Produk

Kalodata Web Scraper Dashboard adalah aplikasi internal Kurma Group untuk mengotomatisasi pengambilan data produk dari **Kalodata** (kalodata.com). Kalodata adalah **satu-satunya** sumber data aplikasi ini.

Scraper berjalan otomatis setiap hari (default pukul 01.00 WIB, dapat diubah di konfigurasi), mengambil data periode **kemarin** untuk tiga negara (Indonesia, Malaysia, Thailand), menyimpan ke PostgreSQL, dan menghasilkan tiga file Excel terpisah per negara yang dapat diunduh dari dashboard.

Kegagalan satu negara tidak boleh menghapus atau menghalangi hasil negara lain.

## 2. Latar Belakang dan Masalah

Pengambilan data Kalodata saat ini manual: buka halaman, pasang filter, buka detail produk, ambil metrik produk dan video terkait. Proses ini berulang setiap hari, lambat, dan rentan salah. Tim riset Kurma Group membutuhkan file Excel harian per negara yang konsisten untuk riset produk fashion (Bawahan Wanita).

Konteks lingkungan:
- VPS Ubuntu sudah berjalan 24 jam dan sudah punya VNC + scraper lain.
- Login Kalodata sejauh ini tidak memerlukan verifikasi tambahan (perlu dikonfirmasi ulang saat PoC).
- Sesi login harus dipertahankan dan dipakai ulang selama valid.

## 3. Tujuan Produk

1. Scraping Kalodata Product otomatis setiap hari dengan filter tetap.
2. Data dan file dipisah per negara (ID, MY, TH).
3. Riwayat hasil tersimpan dan file lama dapat diunduh kembali.
4. Sesi login dikelola aman dan dipakai ulang.
5. Monitoring: status job, log, error, screenshot diagnostik, pemulihan kegagalan.
6. Tidak ada duplikasi data; job yang berhasil tidak terhapus oleh job yang gagal.
7. Satu operator dapat menjalankan dan memantau sistem tanpa membuka terminal.

## 4. Di Luar Cakupan

- Sumber data apa pun selain Kalodata (tidak ada scraping platform lain).
- Mengakali CAPTCHA, OTP, Cloudflare, atau kontrol keamanan platform.
- Menjamin sesi login berlaku selamanya.
- Mengganti akun otomatis tanpa tindakan admin.
- Mengambil data di luar filter yang ditentukan (kategori lain, modul Video/Live/Shop/Influencer) — **boleh disiapkan secara arsitektur** (field `module`), tapi tidak diimplementasi di rilis 1.
- Menjamin selector stabil ketika Kalodata mengubah UI.
- Menggabungkan semua negara ke satu file.
- Memakai API privat Kalodata.
- Notifikasi push/WA/Telegram (disiapkan hook-nya saja, lihat §9.6).
- Multi-tenant / lebih dari satu organisasi.

Scraping harus mematuhi ketentuan layanan dan batas penggunaan Kalodata. Akun yang digunakan adalah akun berbayar milik Kurma Group.

## 5. Pengguna dan Hak Akses

### 5.1 Admin
- Semua yang bisa dilakukan User, ditambah:
- Menjalankan scraping manual (per negara atau semua).
- Mengaktifkan/menonaktifkan jadwal dan mengubah jam jadwal.
- Mengelola konfigurasi akun/profil dan negara.
- Memulai login ulang lewat VNC dan memvalidasi sesi.
- Membatalkan job yang berjalan.
- Melihat log lengkap, screenshot diagnostik, audit log.
- Mengatur retensi.
- Mengelola user dashboard (buat, nonaktifkan, reset password).

### 5.2 User
- Melihat dashboard status.
- Melihat daftar hasil per negara/tanggal dan mengunduh Excel.
- Tidak melihat `profile_path`, log mentah, screenshot, atau pengaturan.

**Keputusan rilis 1:** role User tetap diimplementasi (RBAC sejak awal), tapi hanya satu akun Admin yang dibuat. Pembuatan akun pertama lewat CLI `python -m app.cli create-admin`.

## 6. Sumber Data dan Spesifikasi Scraping

### 6.1 Modul: Kalodata Product (rilis 1)

### 6.2 Filter wajib

| Filter | Nilai yang diinginkan | Catatan implementasi |
|---|---|---|
| Negara/region | ID, MY, TH (bergantian) | Kalodata memiliki pemilih region. Wajib diverifikasi region aktif sebelum ambil data (lihat §6.6). |
| Periode | Kemarin (1 hari kalender) | Gunakan rentang tanggal eksplisit `period_start = period_end = kemarin`, **bukan** preset "Yesterday", agar tanggal yang dipakai tercatat pasti. Jika UI hanya punya preset, pakai preset lalu baca tanggal yang tampil dan simpan. |
| Kategori | Bawahan Wanita | Label aktual di Kalodata kemungkinan berbahasa Inggris dan bertingkat (mis. *Womenswear & Underwear → Women's Bottoms*). Nama persis **wajib diverifikasi** dan dicatat di `config/filters.yaml` per negara (pohon kategori bisa berbeda per negara). |
| Sumber pendapatan | Video | Jika filter ini tersedia di halaman Product, pakai. Jika tidak, lihat fallback §6.4. |

Aturan: jika salah satu label/opsi filter tidak ditemukan **persis** seperti di konfigurasi, job berhenti dengan status `FAILED` dan `error_code = FILTER_NOT_FOUND`. Dilarang memakai filter terdekat.

### 6.3 Bahasa UI

Sebelum scraping, sistem memaksa bahasa UI Kalodata ke satu bahasa tetap (default: **English**) dan memverifikasinya, karena label filter dan format angka berubah mengikuti bahasa. Bahasa ini dicatat di `config/app.yaml` (`kalodata_ui_language`). Nama kategori di `config/filters.yaml` ditulis dalam bahasa tersebut.

### 6.4 Fallback filter "sumber pendapatan = Video"

Urutan yang dicoba:
1. Filter langsung di halaman Product (jika ada) → `revenue_source_method = product_filter`.
2. Jika tidak ada: ambil semua produk kategori, lalu di halaman detail produk baca breakdown pendapatan per sumber (Video/Live/Product Card). Produk disertakan jika pendapatan Video > 0; kolom Pendapatan dan Penjualan yang disimpan adalah **angka dari sumber Video**, bukan total → `revenue_source_method = detail_breakdown`.
3. Jika breakdown juga tidak ada: job berhenti `FAILED` dengan `error_code = REVENUE_SOURCE_UNAVAILABLE`. Agent melapor (§0.3).

Metode yang dipakai dicatat di `scrape_jobs.meta`.

### 6.5 Alur scraping per negara

1. Ambil lock profil browser.
2. Buka browser dengan profil persisten Kalodata.
3. Validasi sesi (§7.4). Jika gagal → `LOGIN_REQUIRED`, lepas lock, job berikutnya yang memakai profil sama di-skip.
4. Set bahasa UI (§6.3), set region negara, **verifikasi region aktif** (§6.6).
5. Buka halaman Product, terapkan filter (§6.2), verifikasi setiap filter tampil aktif di UI.
6. Set ukuran halaman tabel ke nilai terbesar yang tersedia.
7. Baca total hasil (jika UI menampilkan). Jika 0 → `NO_DATA`.
8. Iterasi pagination/infinite scroll sampai habis atau mencapai `max_products_per_country` (default 2.000). Jika terpotong oleh batas → status `PARTIAL`, `meta.truncated = true`.
9. Untuk setiap baris: ambil data yang ada di tabel; simpan **checkpoint** ke DB setiap `checkpoint_every` baris (default 25).
10. Jika kolom wajib belum lengkap atau video belum ditentukan: buka halaman detail produk (tab baru dalam context yang sama), ambil sisanya, pilih satu video (§6.7), tutup tab.
11. Jeda antar aksi sesuai §6.9.
12. Setelah semua baris: validasi (§6.10), set status job, lepas lock.
13. Pembuatan Excel dilakukan oleh job terpisah (§10) agar kegagalan ekspor tidak membatalkan data.

### 6.6 Verifikasi negara

Negara **tidak** boleh diturunkan dari nama file atau asumsi urutan. Setelah mengubah region, sistem membaca kembali indikator region di UI (label region, kode mata uang di tabel, atau URL) dan mencocokkan dengan ekspektasi di `config/countries.yaml`. Jika tidak cocok → `FAILED`, `error_code = COUNTRY_MISMATCH`, tidak ada data yang disimpan.

### 6.7 Aturan pemilihan satu video per produk

Default (**keputusan §19 no. 2**): video dengan **pendapatan tertinggi pada periode yang sama**.

Urutan:
1. Di detail produk, buka daftar video terkait. Jika daftar bisa diurutkan berdasarkan pendapatan/GMV untuk periode yang dipilih → urutkan, ambil teratas → `video_selection_method = top_revenue`.
2. Jika hanya ada urutan berdasarkan penjualan → ambil teratas → `top_sales`.
3. Jika tidak bisa diurutkan tapi ada metrik per video → ambil maksimum pendapatan dari daftar yang tampil (maks `max_videos_scanned`, default 50) → `max_revenue_scanned`.
4. Jika tidak ada metrik → ambil video pertama yang tampil → `first_listed`.
5. Jika tidak ada video sama sekali → `video_url = NULL`, `video_selection_method = none`. Produk **tetap disimpan**.

`video_selection_method` disimpan per baris hasil dan diekspor ke Excel.

Link video yang disimpan: URL TikTok asli (`https://www.tiktok.com/@.../video/...`) jika tersedia; jika hanya ada URL halaman Kalodata video, simpan itu dan tandai `video_url_type = kalodata`.

### 6.8 Kolom yang diambil

| Field DB | Kolom Excel | Wajib | Sumber | Catatan |
|---|---|---|---|---|
| `source_product_id` | ID Produk | Ya | tabel/URL detail | ID TikTok Shop produk (angka panjang). Jika Kalodata hanya punya ID internal, simpan keduanya (`kalodata_product_id`). |
| `product_name` | Nama Produk | Ya | tabel | teks apa adanya |
| `shop_name` | Nama Toko | Ya | tabel/detail | |
| `product_url` | Link Produk | Tidak | detail | ditambahkan di v2.0 |
| `revenue_value` | Pendapatan | Ya | tabel/detail | angka, mata uang lokal (§6.11) |
| `revenue_raw` | — | Ya | tabel | string asli sebelum parsing, untuk audit |
| `sales_value` | Penjualan | Ya | tabel/detail | integer |
| `sales_raw` | — | Ya | tabel | |
| `commission_rate` | Tingkat Komisi | Ya* | tabel/detail | desimal 0–1 (mis. 0.15), Excel format persen. *Boleh NULL jika sumber tidak menampilkan. |
| `commission_raw` | — | | | |
| `video_url` | Link Video | Ya* | detail | *NULL diizinkan (§6.7 no. 5) |
| `video_selection_method` | Metode Pilih Video | Ya | sistem | |
| `currency_code` | Mata Uang | Ya | config/UI | IDR / MYR / THB |
| `country_code` | Negara | Ya | §6.6 | ID / MY / TH |
| `period_start`, `period_end` | Periode Data | Ya | sistem | tanggal, keduanya sama untuk rilis 1 |
| `scraped_at` | Waktu Scraping | Ya | sistem | WIB di Excel, UTC di DB |
| `scrape_job_id` | Job ID | Ya | sistem | |

### 6.9 Pacing dan pembatasan

- Satu browser context aktif per profil; tidak ada paralelisme antar negara pada profil sama.
- Jeda acak antar navigasi halaman: `delay_page_min..max` (default 2–5 detik).
- Jeda antar pembukaan detail produk: `delay_detail_min..max` (default 1,5–4 detik).
- Maks produk per negara per run: 2.000. Maks detail dibuka per run: sama.
- Maks durasi job per negara: `job_timeout_minutes` (default 90).
- Jika terdeteksi halaman challenge/blokir (Cloudflare, "too many requests", 429) → hentikan job `FAILED`, `error_code = ACCESS_RESTRICTED`, jangan retry otomatis pada hari yang sama.
- Satu run harian total maks `daily_run_timeout_minutes` (default 300).

### 6.10 Validasi data

Sebelum baris disimpan:
- `source_product_id` tidak kosong dan cocok pola yang dikonfigurasi.
- `revenue_value >= 0`, `sales_value >= 0`, `0 <= commission_rate <= 1` (jika ada).
- `video_url` kosong atau URL valid.
- Baris gagal validasi → tidak disimpan ke hasil, tapi dicatat di `scrape_job_rows_rejected` dengan alasan. Job tetap lanjut. Jika rejected > `max_reject_ratio` (default 20%) → status `PARTIAL`.

### 6.11 Parsing angka dan mata uang per negara

Kalodata menampilkan angka singkat (contoh ekspektasi: `Rp 1,2jt`, `RM12.5K`, `฿1.2M`, `1.2K`). Aturan:
- Parser mengambil dari `config/number_formats.yaml` per negara dan bahasa UI: simbol mata uang, pemisah ribuan/desimal, sufiks (K, M, B, rb, jt, M, 万 dll).
- Simpan `*_raw` selalu; `*_value` hasil parsing.
- Jika parsing gagal → `*_value = NULL`, baris masuk `rejected` jika kolom wajib.
- Nilai yang dibulatkan Kalodata (mis. "1.2M") disimpan apa adanya sebagai 1.200.000; kolom `revenue_is_abbreviated = true` dicatat agar user tahu angkanya pembulatan. Jika halaman detail menampilkan angka penuh, utamakan angka penuh.
- **Semua format aktual wajib diverifikasi di Tahap 2 dan dicatat dengan contoh nyata per negara.**

## 7. Pengelolaan Negara dan Akun

### 7.1 Model akun (**keputusan §19 no. 1**)

Default: **satu akun Kalodata mengakses ketiga negara dengan satu profil browser**, job negara dijalankan serial dengan mengganti region. Skema data tetap mendukung banyak profil (`account_profiles.country_scope` = daftar kode negara) agar bisa dipisah tanpa migrasi besar jika ternyata akun berbeda.

### 7.2 Profil browser

- Direktori: `runtime/profiles/kalodata/<account_label>/` (Playwright `launch_persistent_context`).
- Terpisah total dari profil scraper lain di VPS.
- Izin: `0700`, pemilik = user service `kalodata`.
- Dikecualikan dari Git (`.gitignore`), dari backup kode, dan dari log.
- Satu proses per direktori profil, dijaga oleh lock file + lock Redis (`lock:profile:<id>`, TTL = job timeout).

### 7.3 Login awal / login ulang (via VNC)

1. Admin klik **Buka Browser untuk Login** di dashboard (atau CLI `python -m app.cli open-login --profile default`).
2. Worker membuka Chromium **headful** pada `DISPLAY` yang dikonfigurasi (`KALODATA_DISPLAY`, default `:1` — sesuaikan dengan VNC yang ada) dengan profil persisten, menuju halaman login Kalodata.
3. Admin login manual lewat VNC viewer. Sistem **tidak** mengisi username/password.
4. Status profil = `WAITING_FOR_VERIFICATION` sampai admin klik **Validasi Sesi** atau sistem mendeteksi login sukses (poll setiap 10 detik, maks 20 menit, lalu browser ditutup dan status `LOGIN_REQUIRED`).
5. Setelah valid → `READY`, `last_validated_at` diisi, browser ditutup.
6. Scheduler harian memakai profil ini tanpa VNC.

### 7.4 Validasi sesi

Dilakukan: sebelum setiap run harian, saat admin klik Validasi, dan setiap `session_check_interval_hours` (default 6) sebagai health check ringan.

Prosedur: buka halaman yang hanya bisa diakses setelah login (mis. halaman Product), tunggu sampai `selectors.logged_in_indicator` muncul **atau** `selectors.login_page_indicator` muncul, maks 30 detik. Hasil: `READY` / `LOGIN_REQUIRED` / `ERROR` (timeout, challenge, jaringan).

### 7.5 Status sesi

`READY`, `LOGIN_REQUIRED`, `WAITING_FOR_VERIFICATION`, `VALIDATING`, `DISABLED`, `ERROR`. Transisi dicatat di `audit_logs`.

### 7.6 Mode headless vs headful

- Login dan debugging: headful di DISPLAY VNC.
- Scraping terjadwal: default **headful di DISPLAY yang sama** (lebih aman dari deteksi bot). Headless hanya diaktifkan (`KALODATA_HEADLESS=true`) setelah diuji minimal 3 run berturut-turut tanpa perbedaan hasil. Keduanya memakai profil yang sama.
- Jika X server/VNC tidak tersedia saat job berjalan → `FAILED`, `error_code = DISPLAY_UNAVAILABLE`.

## 8. Scheduler dan Operasi 24/7

### 8.1 Jadwal

- Default: setiap hari **01.00 WIB** (`cron: 0 1 * * *`, tz `Asia/Jakarta`), dapat diubah admin.
- Periode data = hari kalender sebelum tanggal run, menurut **zona waktu Kalodata** (lihat §8.4).
- Scheduler = Celery Beat **satu instance** dengan lock Redis `lock:beat`; tidak pernah dijalankan di proses web.

### 8.2 Urutan run harian

1. `healthcheck` — DB, Redis, DISPLAY, disk ≥ `min_free_disk_mb` (default 2.000).
2. `validate_session` — per profil aktif.
3. `scrape_product` ID → MY → TH (serial jika profil sama; urutan dari `config/countries.yaml`).
4. `export_excel` per negara yang statusnya `SUCCESS`/`PARTIAL`/`NO_DATA` (yang terakhir hanya jika `export_empty_file = true`).
5. `finalize_run` — ringkasan run, notifikasi hook.
6. `cleanup_retention` (jam 03.00 WIB, terpisah).

### 8.3 Keandalan

- Timeout per job dan per run (§6.9).
- Retry: hanya untuk `NETWORK_ERROR` dan `PAGE_TIMEOUT`, maks 3× dengan backoff 30s/120s/300s, **melanjutkan dari checkpoint**, bukan dari awal.
- Tidak ada retry untuk `LOGIN_REQUIRED`, `FILTER_NOT_FOUND`, `COUNTRY_MISMATCH`, `SELECTOR_CHANGED`, `ACCESS_RESTRICTED`.
- Lock per profil dan per (negara, periode) — job ganda ditolak dengan status `SKIPPED_DUPLICATE`.
- Worker crash/reboot: job yang `RUNNING` lebih lama dari timeout saat startup ditandai `FAILED` (`error_code = WORKER_LOST`); data checkpoint tetap ada dan admin bisa **Resume**.
- Semua service `restart: unless-stopped` (Docker) / `Restart=always` (systemd).

### 8.4 Ketersediaan data "kemarin" (RISIKO UTAMA — wajib diuji Tahap 2)

Kalodata mungkin belum menyediakan data hari kemarin secara lengkap pada pukul 01.00 WIB (data platform analitik umumnya tertunda beberapa jam dan zona waktu Kalodata bisa berbeda dari WIB). Agent wajib:
1. Mencatat zona waktu yang dipakai Kalodata di tanggal/periode (uji dengan membandingkan data pada beberapa jam berbeda).
2. Mengimplementasikan pemeriksaan **readiness**: sebelum scraping, baca indikator "data updated at"/tanggal terakhir yang tersedia (jika ada) atau cek apakah pilihan tanggal kemarin menghasilkan baris. Jika belum siap → status `DATA_NOT_READY`, jadwalkan ulang otomatis setiap `readiness_retry_minutes` (default 60) sampai `readiness_deadline_hour` (default 10.00 WIB), lalu `FAILED`.
3. Merekomendasikan jam jadwal final ke pemilik produk berdasarkan temuan (jam 01.00 adalah titik awal, bukan keharusan).

### 8.5 State machine job

```
PENDING → RUNNING → SUCCESS
                  → PARTIAL          (ada data, tidak lengkap/terpotong/rejected tinggi)
                  → NO_DATA          (filter valid, 0 baris)
                  → DATA_NOT_READY   (akan dicoba lagi)
                  → LOGIN_REQUIRED
                  → FAILED           (error_code wajib diisi)
                  → CANCELLED        (oleh admin)
PENDING → SKIPPED_DUPLICATE
PENDING → SKIPPED_SESSION  (profil tidak READY)
```
Status terminal: `SUCCESS`, `PARTIAL`, `NO_DATA`, `FAILED`, `CANCELLED`, `SKIPPED_*`. Hanya job terminal yang bisa di-Resume (menjadi job baru dengan `resumed_from_job_id`).

Kode error standar: `LOGIN_REQUIRED`, `FILTER_NOT_FOUND`, `COUNTRY_MISMATCH`, `SELECTOR_CHANGED`, `PAGE_TIMEOUT`, `NETWORK_ERROR`, `ACCESS_RESTRICTED`, `DISPLAY_UNAVAILABLE`, `DB_UNAVAILABLE`, `EXPORT_FAILED`, `WORKER_LOST`, `VALIDATION_FAILED`, `UNKNOWN`.

### 8.6 Pembatalan job

Admin dapat membatalkan job `RUNNING`. Worker memeriksa flag cancel setiap selesai satu produk; menutup browser dengan rapi; data checkpoint tetap tersimpan; status `CANCELLED`.

## 9. Dashboard dan Halaman

Semua waktu ditampilkan dalam WIB dengan label "WIB". Semua teks UI Bahasa Indonesia.

### 9.1 Dashboard (`/`)
- Status worker, scheduler (aktif/nonaktif, jadwal berikutnya WIB), Redis, DB, DISPLAY.
- Kartu per negara: status job terakhir, jumlah baris, durasi, tautan download.
- Status sesi tiap profil + tombol aksi cepat.
- Daftar job yang butuh perhatian (`LOGIN_REQUIRED`, `FAILED`, `PARTIAL`, `DATA_NOT_READY`).
- Disk tersisa dan jumlah file tersimpan.

### 9.2 Hasil & Ekspor (`/results`)
- Filter: negara, rentang periode, status.
- Kolom: negara, periode, waktu scraping, baris, status, nama file, Download, Ekspor Ulang (admin).
- Preview 50 baris pertama di web (admin dan user).

### 9.3 Manajemen Akun (`/accounts`, admin)
- Daftar profil: label, cakupan negara, status sesi, terakhir divalidasi, catatan.
- Tombol: Buka Browser untuk Login, Validasi Sesi, Nonaktifkan, Edit catatan.
- Instruksi langkah login lewat VNC ditampilkan inline (tanpa menampilkan alamat/port VNC jika `show_vnc_hint=false`).
- `profile_path` tidak pernah ditampilkan.

### 9.4 Jadwal & Job (`/jobs`)
- Jadwal: aktif/nonaktif, jam (WIB), simpan.
- Jalankan manual: pilih negara (satu/semua) dan periode (default kemarin; admin boleh pilih tanggal lain maks 30 hari ke belakang).
- Daftar job dengan progres (baris diproses/ditemukan), tahap saat ini, tombol Batalkan/Resume.

### 9.5 Riwayat & Log (`/jobs/<id>`)
- Timeline tahap dengan timestamp.
- Ringkasan error dalam bahasa manusia + `error_code`.
- Counter: ditemukan, disimpan, dilewati, duplikat, rejected.
- Daftar screenshot diagnostik (admin, diunduh lewat endpoint terproteksi).
- Log mentah 500 baris terakhir (admin).

### 9.6 Pengaturan (`/settings`, admin)
- Retensi (file, screenshot, log), `export_empty_file`, batas produk, jam readiness.
- Webhook URL notifikasi (opsional, POST JSON ringkasan run; tidak ada integrasi spesifik di rilis 1).
- Audit log viewer.

### 9.7 Halaman sistem
- `/login`, `/logout`, `/health` (tanpa auth, JSON: status DB/Redis/worker), `/metrics` (opsional, Prometheus, dibatasi IP).

## 10. File Excel dan Penyimpanan

### 10.1 Penamaan

`Product_{COUNTRY}_run-{RUN_DATE}_data-{PERIOD}_{STATUS}.xlsx`
Contoh: `Product_ID_run-2026-10-17_data-2026-10-16_SUCCESS.xlsx`, `..._PARTIAL.xlsx`.
Ekspor ulang menambah sufiks `_v2`, `_v3`; file lama tidak ditimpa.

Lokasi: `runtime/exports/{YYYY}/{MM}/`. Nama file divalidasi (whitelist karakter) sebelum disajikan.

### 10.2 Format workbook

- Sheet `Data`: header baris 1 (freeze panes), AutoFilter, lebar kolom otomatis.
- Urutan kolom: ID Produk, Nama Produk, Nama Toko, Link Produk, Pendapatan, Penjualan, Tingkat Komisi, Link Video, Metode Pilih Video, Mata Uang, Negara, Periode Data, Waktu Scraping (WIB), Job ID.
- Tipe: ID Produk sebagai **teks** (hindari notasi ilmiah), Pendapatan numerik dengan format mata uang negara (`Rp #,##0`, `RM #,##0.00`, `฿#,##0.00`), Penjualan integer, Komisi format `0.00%`, link sebagai hyperlink.
- Sheet `Info`: negara, periode, waktu scraping, status job, metode filter sumber pendapatan, jumlah baris, jumlah rejected, versi aplikasi, catatan jika PARTIAL/truncated.
- Jika status `NO_DATA` dan `export_empty_file=true`: workbook hanya berisi header + sheet Info.
- Library: openpyxl.

### 10.3 Retensi (**keputusan §19 no. 5**)

| Objek | Default |
|---|---|
| File Excel | 180 hari |
| Data hasil di DB | tidak dihapus (ringan) |
| Screenshot diagnostik | 30 hari |
| Log aplikasi | 30 hari (rotasi harian) |
| Audit log | 365 hari |

Dapat diubah di Pengaturan. Penghapusan dicatat di audit log.

## 11. Model Data

Semua timestamp disimpan **UTC** (`timestamptz`); tanggal periode sebagai `date`. ID memakai UUID. Migrasi lewat Alembic.

### `users`
`id, username, password_hash (argon2/bcrypt), role (admin|user), is_active, created_at, last_login_at`

### `account_profiles`
`id, source='kalodata', account_label, country_scope (text[]), profile_dir_name (relatif, bukan path absolut), ui_language, session_status, last_validated_at, last_login_at, last_account_change_at, enabled, notes, created_at, updated_at`

### `scrape_runs`
Satu run harian = satu baris. `id, trigger (scheduled|manual), period_start, period_end, status, started_at, finished_at, created_by, summary (jsonb)`

### `scrape_jobs`
`id, run_id, source='kalodata', module='product', country_code, account_profile_id, period_start, period_end, status, error_code, error_summary, stage, started_at, finished_at, rows_found, rows_saved, rows_rejected, rows_duplicate, retry_count, resumed_from_job_id, checkpoint (jsonb: page, last_index, last_product_id), meta (jsonb: revenue_source_method, truncated, ui_language, headless), created_by, created_at`

Index: `(country_code, period_start, status)`. Unique partial: tidak boleh ada dua job `RUNNING` dengan `(country_code, period_start)` sama.

### `products`
`id, source_product_id, kalodata_product_id, country_code, product_name, shop_name, product_url, first_seen_at, last_seen_at`
Unique: `(country_code, source_product_id)`.

### `kalodata_product_results`
`id, scrape_job_id, product_id, source_product_id, country_code, period_start, period_end, product_name, shop_name, product_url, revenue_value (numeric 18,2), revenue_raw, revenue_is_abbreviated, sales_value (int), sales_raw, commission_rate (numeric 6,4), commission_raw, currency_code, video_url, video_url_type, video_selection_method, scraped_at`
**Unique: `(country_code, source_product_id, period_start, period_end)`** — simpan dengan upsert; run ulang periode yang sama memperbarui baris dan menaikkan `rows_duplicate` pada job.

### `scrape_job_rows_rejected`
`id, scrape_job_id, row_index, reason, raw (jsonb), created_at`

### `export_files`
`id, scrape_job_id, country_code, module, period_start, period_end, file_name, relative_path, row_count, status (SUCCESS|FAILED|EMPTY), version, size_bytes, checksum_sha256, created_at, deleted_at`

### `diagnostic_screenshots`
`id, scrape_job_id, stage, relative_path, created_at, deleted_at`

### `settings`
`key, value (jsonb), updated_by, updated_at`

### `audit_logs`
`id, actor_id, action, target_type, target_id, ip, timestamp, details (jsonb, tanpa rahasia)`

## 12. Teknologi dan Versi

| Komponen | Pilihan | Versi minimum |
|---|---|---|
| Bahasa | Python | 3.11 |
| Browser automation | Playwright (Python) + Chromium bawaan Playwright | terbaru stabil |
| Web | Flask + Jinja2, Flask-Login, Flask-WTF (CSRF) | Flask 3 |
| ORM/migrasi | SQLAlchemy 2 + Alembic | |
| DB | PostgreSQL | 15 |
| Queue/lock | Redis 7 + Celery 5 (+ Beat) | |
| Server | Gunicorn (web) di belakang Nginx (TLS) | |
| Ekspor | openpyxl | |
| Konfigurasi | `.env` (rahasia) + `config/*.yaml` (non-rahasia) | |
| Log | JSON terstruktur (structlog), rotasi harian | |
| Test | pytest, pytest-playwright | |
| Lint | ruff, mypy (ringan) | |

React **tidak** dipakai di rilis 1.

## 13. Deployment dan Browser

### 13.1 Prasyarat VPS (dicek Tahap 1)

- Ubuntu 22.04/24.04, RAM bebas ≥ 2 GB saat scraper lain berjalan, disk bebas ≥ 10 GB, Docker ≥ 24 + Compose v2.
- X server/VNC yang ada: catat `DISPLAY` yang dipakai, user pemiliknya, dan apakah sesi bertahan tanpa klien terhubung.
- Port bebas untuk web internal (default 8081), Postgres (hanya internal Docker), Redis (internal).

### 13.2 Keputusan arsitektur proses (menyelesaikan konflik Docker vs GUI)

- **Dalam Docker Compose:** `web` (Flask/Gunicorn), `beat` (scheduler), `db` (Postgres), `redis`, `nginx` (opsional jika Nginx host sudah ada).
- **Di luar Docker, sebagai systemd service di host:** `kalodata-worker` (Celery worker yang menjalankan Playwright). Alasan: akses langsung ke DISPLAY/X server VNC yang sudah ada, menghindari X11 passthrough dari container, dan profil browser tetap di filesystem host.
- Worker terhubung ke Postgres/Redis lewat port yang di-bind ke `127.0.0.1` saja.
- Jika kelak ingin worker di Docker: mount `/tmp/.X11-unix`, set `DISPLAY`, `xhost` terbatas — di luar rilis 1.
- Concurrency worker = 1; queue `kalodata`.

### 13.3 Struktur proyek

```text
kalodata-scraper-dashboard/
├── app/
│   ├── __init__.py            # create_app()
│   ├── cli.py                 # scrape, export, open-login, validate-session, create-admin
│   ├── config.py              # load .env + config/*.yaml
│   ├── routes/                # dashboard, results, accounts, jobs, settings, auth, api
│   ├── services/              # session_service, job_service, export_service, retention_service
│   ├── scrapers/
│   │   ├── base.py            # browser lifecycle, lock, screenshot, pacing
│   │   ├── kalodata/
│   │   │   ├── session.py     # login/validate
│   │   │   ├── navigation.py  # language, region, filters
│   │   │   ├── product_list.py
│   │   │   ├── product_detail.py
│   │   │   └── parsers.py     # angka/mata uang
│   ├── tasks/                 # celery tasks: healthcheck, validate, scrape, export, cleanup
│   ├── models/
│   ├── exports/excel.py
│   ├── templates/
│   └── static/
├── config/
│   ├── app.yaml               # jadwal default, batas, retensi default
│   ├── countries.yaml         # ID/MY/TH: region label, currency, expected indicators
│   ├── filters.yaml           # label kategori & sumber pendapatan per negara/bahasa
│   ├── selectors.yaml         # semua selector (lihat §13.4)
│   └── number_formats.yaml
├── runtime/                   # .gitignore seluruhnya
│   ├── profiles/kalodata/
│   ├── exports/
│   ├── logs/
│   ├── screenshots/
│   └── locks/
├── docs/
│   ├── KALODATA_UI_NOTES.md   # hasil verifikasi UI (Tahap 1–2)
│   ├── REPORT_TAHAP_*.md
│   └── RUNBOOK.md             # operasional: login ulang, resume, restore
├── tests/
│   ├── unit/                  # parsers, naming, validasi
│   ├── fixtures/html/         # snapshot HTML Kalodata (disanitasi)
│   └── e2e/                   # butuh sesi nyata, ditandai @live
├── migrations/
├── deploy/
│   ├── kalodata-worker.service
│   └── nginx.conf
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── pyproject.toml
└── README.md
```

### 13.4 Selector eksternal

Semua selector hidup di `config/selectors.yaml` dengan struktur `{nama: {primary, fallbacks[], kind: css|text|role}}`. Kode memanggil `sel("product_table_row")`. Setiap selector wajib punya minimal satu fallback. Utamakan `get_by_role`/`get_by_text` untuk teks yang stabil, hindari class hash. Smoke test selector (`python -m app.cli smoke-selectors`) memverifikasi semua selector ditemukan pada halaman nyata dan dijalankan sebelum run harian (gagal → `SELECTOR_CHANGED`, run dibatalkan sebelum menyentuh data).

### 13.5 Variabel lingkungan (`.env.example`)

```
APP_ENV=production
SECRET_KEY=
DATABASE_URL=postgresql+psycopg://kalodata:***@127.0.0.1:5433/kalodata
REDIS_URL=redis://127.0.0.1:6380/0
TZ=Asia/Jakarta
KALODATA_BASE_URL=https://www.kalodata.com
KALODATA_UI_LANGUAGE=en
KALODATA_DISPLAY=:1
KALODATA_HEADLESS=false
RUNTIME_DIR=/opt/kalodata/runtime
WEB_PORT=8081
LOG_LEVEL=INFO
WEBHOOK_URL=
```
Tidak ada username/password Kalodata di env.

## 14. Keamanan

- Login dashboard: password hash argon2, rate limit login, sesi cookie `Secure/HttpOnly/SameSite=Lax`, CSRF di semua form.
- RBAC Admin/User di setiap route (decorator), termasuk endpoint download dan screenshot.
- HTTPS via Nginx (Let's Encrypt) atau hanya bind `127.0.0.1` + SSH tunnel jika tanpa domain.
- VNC tidak dibuka publik; SSH tunnel/whitelist IP (tidak diubah oleh proyek ini).
- Profil browser, cookies, storage state = kredensial: `0700`, tidak masuk log/UI/Git/backup kode.
- Download: hanya file yang terdaftar di `export_files`, path dibangun dari `relative_path` + root tetap, tolak `..`.
- Screenshot diagnostik: dipotong/dimask area yang berisi email/nama akun jika memungkinkan; akses admin saja.
- Log: redaksi otomatis pola cookie/token/email.
- Audit: login, perubahan jadwal, run manual, cancel, login ulang, validasi, download (admin saja), perubahan retensi.
- Dependensi dipin (`pyproject.toml` + lockfile).

## 15. Penanganan Error

| Situasi | error_code | Perilaku |
|---|---|---|
| Sesi kedaluwarsa | `LOGIN_REQUIRED` | profil → `LOGIN_REQUIRED`, job dan job berikutnya pada profil sama → `SKIPPED_SESSION`; dashboard tampilkan instruksi |
| Region tidak sesuai | `COUNTRY_MISMATCH` | berhenti sebelum ambil data |
| Label filter/kategori tidak ada | `FILTER_NOT_FOUND` | berhenti, screenshot, tidak ada retry |
| Selector tidak ditemukan | `SELECTOR_CHANGED` | screenshot + HTML dump, tidak ada retry |
| Timeout halaman | `PAGE_TIMEOUT` | retry 3× dari checkpoint |
| Gangguan jaringan | `NETWORK_ERROR` | retry backoff dari checkpoint |
| Challenge/429/blokir | `ACCESS_RESTRICTED` | berhenti, tidak retry hari itu, tandai perhatian |
| 0 hasil, filter valid | — (`NO_DATA`) | status NO_DATA |
| Data kemarin belum ada | — (`DATA_NOT_READY`) | jadwal ulang per §8.4 |
| DISPLAY tidak ada | `DISPLAY_UNAVAILABLE` | berhenti |
| DB down | `DB_UNAVAILABLE` | jangan klaim sukses, checkpoint di memori ditulis ulang saat DB kembali (maks 5 menit), lalu FAILED |
| Ekspor gagal | `EXPORT_FAILED` | data tetap, `export_files.status=FAILED`, tombol Ekspor Ulang |
| Worker hilang | `WORKER_LOST` | job → FAILED saat startup, bisa Resume |
| Satu negara gagal | — | negara lain tetap jalan kecuali `LOGIN_REQUIRED`/`ACCESS_RESTRICTED` pada profil sama |

## 16. Kriteria Penerimaan

### Verifikasi UI (Tahap 1–2)
- [ ] `docs/KALODATA_UI_NOTES.md` berisi: label kategori per negara, label filter sumber pendapatan (atau bukti ketiadaannya), zona waktu Kalodata, jam ketersediaan data kemarin, contoh format angka tiap negara, cara menentukan video terlaris.
- [ ] Semua selector di `config/selectors.yaml` lolos `smoke-selectors`.

### Scraping
- [ ] Periode kemarin diterapkan dan tanggal yang tampil di UI sama dengan yang disimpan.
- [ ] Kategori dan sumber pendapatan diterapkan sesuai konfigurasi; label tidak ada → `FILTER_NOT_FOUND`.
- [ ] Region diverifikasi sebelum ambil data; mismatch → tidak ada data tersimpan.
- [ ] Seluruh halaman diproses; terpotong batas → `PARTIAL` + `truncated`.
- [ ] Satu video per produk dengan `video_selection_method` tercatat; produk tanpa video tetap tersimpan.
- [ ] `*_raw` tersimpan untuk semua angka; parsing gagal → NULL, bukan 0.
- [ ] Checkpoint: job dimatikan paksa di tengah, Resume melanjutkan tanpa duplikasi.
- [ ] Run ulang periode sama tidak menggandakan baris (upsert).

### Akun dan sesi
- [ ] Sesi dipakai ulang setelah browser ditutup dan worker restart.
- [ ] Profil terpisah dari scraper lain; izin `0700`.
- [ ] Login ulang via VNC dari dashboard berfungsi; sistem tidak pernah memasukkan password.
- [ ] Job tidak jalan jika profil bukan `READY`.
- [ ] Dua proses tidak bisa memakai profil sama (uji lock).

### Scheduler dan keandalan
- [ ] Run otomatis pada jam terkonfigurasi (WIB), dashboard tertutup.
- [ ] Beat hanya satu instance; job ganda → `SKIPPED_DUPLICATE`.
- [ ] Kegagalan satu negara tidak menghapus negara lain.
- [ ] Reboot VPS: semua service kembali, job `RUNNING` yang hilang → `FAILED` + Resume tersedia.
- [ ] `DATA_NOT_READY` menjadwalkan ulang dan berhenti di deadline.

### Ekspor dan dashboard
- [ ] Tiga file terpisah, nama sesuai §10.1, status PARTIAL terlihat di nama dan sheet Info.
- [ ] ID Produk tidak berubah jadi notasi ilmiah; komisi tampil persen; mata uang sesuai negara.
- [ ] File lama bisa diunduh sampai retensi; ekspor ulang membuat versi baru.
- [ ] User tidak bisa mengakses halaman admin, screenshot, atau `profile_path` (uji manual + test).
- [ ] `/health` mengembalikan status komponen.

### Kualitas
- [ ] Unit test parser angka ≥ 20 kasus (per negara, per sufiks, kasus gagal).
- [ ] Test e2e `@live` 1 produk per negara lolos.
- [ ] Hasil 3 hari berturut-turut dibandingkan manual dengan Kalodata: selisih baris 0, selisih nilai ≤ pembulatan Kalodata.

## 17. Tahapan Implementasi dan Deliverable

| Tahap | Isi | Deliverable (wajib ada sebelum lanjut) |
|---|---|---|
| 1. Audit VPS & sumber | cek spesifikasi, DISPLAY, service, port; jelajahi Kalodata manual | `docs/REPORT_TAHAP_1.md`, draft `KALODATA_UI_NOTES.md`, daftar port/DISPLAY |
| 2. PoC | script Playwright CLI: login reuse, set bahasa, set region, filter, baca 1 halaman, buka 1 detail, pilih video, parse angka — untuk **ketiga negara** | `app/cli.py scrape --limit 5` jalan; output JSON 5 produk/negara; `selectors.yaml`, `filters.yaml`, `number_formats.yaml` terisi; temuan readiness data (§8.4); `REPORT_TAHAP_2.md` |
| 3. DB & ekspor | model, migrasi, upsert, checkpoint, Excel | `cli export` menghasilkan 3 xlsx dari DB; unit test parser |
| 4. Sesi | profil persisten, lock, validasi, open-login | uji restart browser/worker; uji lock ganda |
| 5. Dashboard | semua halaman §9, RBAC, run manual, cancel/resume | akun admin via CLI; screenshot tiap halaman di report |
| 6. Scheduler & deploy | Compose, systemd worker, Beat lock, retry, timeout, retensi, Nginx | runbook `docs/RUNBOOK.md`; uji reboot VPS |
| 7. Uji operasional | 3–5 hari run nyata, bandingkan manual, uji skenario error | `REPORT_TAHAP_7.md` dengan tabel perbandingan; rekomendasi jam jadwal final |

## 18. Risiko dan Mitigasi

| Risiko | Mitigasi |
|---|---|
| Data kemarin belum tersedia jam 01.00 | readiness check + reschedule (§8.4), jam jadwal konfigurabel |
| Perubahan UI Kalodata | selector eksternal + fallback, smoke test sebelum run, screenshot+HTML dump |
| Bahasa UI berubah → label beda | paksa bahasa tetap dan verifikasi (§6.3) |
| Kategori beda per negara | `filters.yaml` per negara |
| Deteksi bot / pembatasan | headful, pacing acak, 1 context, berhenti saat challenge |
| Sesi kedaluwarsa | validasi sebelum run + health check berkala + login ulang via VNC |
| Profil terkunci oleh proses lain | lock file + Redis, 1 worker |
| Angka singkat (1.2M) tidak presisi | simpan raw + flag abbreviated; utamakan angka penuh dari detail |
| Job terlalu lama | timeout, checkpoint, batas produk, serial |
| Duplikasi | unique key + upsert |
| VPS kehabisan disk/RAM | healthcheck disk, retensi, batas produk |
| Profil/kredensial bocor | izin ketat, redaksi log, tidak di Git, akses admin saja |
| Scraper lain terganggu | prefix `kalodata-`, port terpisah, DISPLAY dipakai bersama hanya saat login/scrape dengan window terpisah; tidak mengubah konfigurasi VNC |

## 19. Keputusan Default (menggantikan "Pertanyaan Terbuka")

Agent memakai nilai ini kecuali temuan Tahap 1–2 membuktikan sebaliknya.

| No | Pertanyaan | Keputusan default |
|---|---|---|
| 1 | Satu akun untuk tiga negara? | **Ya, satu akun, satu profil**, job serial ganti region. Skema mendukung multi-profil. |
| 2 | "Satu video" = ? | **Video pendapatan tertinggi pada periode**, dengan urutan fallback §6.7. |
| 3 | Jumlah produk per negara per hari | Asumsi ≤ 500; batas keras 2.000 → `PARTIAL`. Laporkan angka nyata di Tahap 2. |
| 4 | File kosong saat NO_DATA? | **Tidak dibuat** (`export_empty_file=false`); status NO_DATA tampil di dashboard. |
| 5 | Retensi | Excel 180 hari, screenshot 30 hari, log 30 hari, audit 365 hari. |
| 6 | Format mata uang/komisi | Simpan raw + parsed; currency IDR/MYR/THB dari `countries.yaml`; komisi desimal 0–1. Format aktual diverifikasi Tahap 2. |
| 7 | Jam jadwal | 01.00 WIB sebagai awal; final ditentukan setelah temuan readiness (§8.4). |
| 8 | Headless? | Tidak untuk rilis 1 (headful di DISPLAY VNC). |
| 9 | Worker di Docker? | Tidak; systemd di host (§13.2). |
| 10 | Bahasa UI Kalodata | English. |
| 11 | Ekspor dipicu | Otomatis setelah job negara terminal dengan data; bisa diulang manual. |

## 20. Definition of Done (rilis 1)

- Semua checklist §16 terpenuhi dan terdokumentasi di `REPORT_TAHAP_7.md`.
- `docs/RUNBOOK.md` menjelaskan: login ulang, resume job, ekspor ulang, cek log, restore setelah reboot, cara memperbarui selector.
- `README.md` menjelaskan setup dari nol di VPS (tanpa langkah yang menyentuh scraper lain).
- Pemilik produk telah membandingkan hasil minimal 3 hari dan menyetujui akurasi.
- Tidak ada rahasia di repo (dicek dengan scan sederhana).

## 21. Glosarium

- **Run**: satu eksekusi harian yang mencakup semua negara.
- **Job**: satu negara dalam satu run.
- **Profil**: direktori data browser persisten yang menyimpan sesi login.
- **Periode data**: tanggal yang datanya diambil (kemarin). **Tanggal run**: tanggal job dijalankan.
- **Checkpoint**: posisi terakhir (halaman/index/produk) yang tersimpan agar job bisa dilanjutkan.
- **PARTIAL**: ada data, tapi tidak lengkap karena terpotong batas, timeout, atau rejected tinggi.
- **Readiness**: kondisi data kemarin sudah tersedia di Kalodata.
