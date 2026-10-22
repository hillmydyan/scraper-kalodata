# Laporan Tahap 3: Implementasi End-to-End Scraper Kalodata & Dashboard

**Tanggal:** 19 Oktober 2026  
**Status:** Berhasil Diuji & Terverifikasi (End-to-End Live Execution Berhasil)  
**Tautan Terkait:**
- PRD: [PRD_Kalodata_Web_Scraper_Dashboard_v2 (1).md](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/PRD_Kalodata_Web_Scraper_Dashboard_v2%20(1).md)
- Observasi UI: [docs/KALODATA_UI_NOTES.md](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/docs/KALODATA_UI_NOTES.md)
- Konfigurasi Selektor: [config/selectors.yaml](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/config/selectors.yaml)
- Engine Scraper: [app/scrapers/kalodata/product_list.py](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/app/scrapers/kalodata/product_list.py)

---

## 1. Integrasi Profil Chrome Pengguna
Sesuai instruksi pengguna, engine scraper menggunakan direktori profil Chrome yang sudah ada:
`C:\Users\User\Downloads\PROJECT\scrapper_tiktok\chrome_profile`

- **Konfigurasi:** Ditambahkan pada [app/config.py](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/app/config.py) dan `.env` sebagai `CHROME_USER_DATA_DIR`.
- **Eksekusi:** [app/scrapers/base.py](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/app/scrapers/base.py) otomatis mendeteksi profil ini dan meluncurkan Google Chrome asli di desktop Windows tanpa meminta operator login ulang.

---

## 2. Reverse Engineering UI Aktual Kalodata (`kalodata.com`)

| Komponen | Lokasi UI Aktual | Selector Terverifikasi | Catatan Implementasi |
| :--- | :--- | :--- | :--- |
| **Pemilih Region** | Header kiri atas (Ikon bendera) | `header div[class*='bg-cover'][style*='background-image']` | Membuka popover negara (Indonesia `ID`, Malaysia `MY`, Thailand `TH`). |
| **Filter Tanggal** | Sidebar kiri `Filters` &rarr; `Dates` | `div.inline-flex.items-center:has-text('Dates')` | Memilih opsi preset `Yesterday` secara instan. |
| **Filter Kategori** | Sidebar kiri `Filters` &rarr; `Category` | `div.inline-flex.items-center:has-text('Category')` | Ant Design Cascader Popover: `Womenswear & Underwear` &rarr; centang `Women's Bottoms` &rarr; klik `Apply`. |
| **Tombol Submit Filter** | Bagian bawah sidebar kiri | `button:has-text('Submit')` | Menerapkan filter ke tabel produk Kalodata. |
| **Tabel Produk** | Area utama halaman | `tbody tr.group` | Menggunakan layout tabel Tailwind CSS (`tr.group.cursor-pointer`). |
| **Ekstraksi ID Produk** | Gambar thumbnail cover pada kolom produk | `div[style*='/tiktok.product/']` | ID numerik unik diekstrak langsung dari CDN URL cover (`/tiktok.product/{id}/cover.png`). |
| **Paginasi** | Navigasi halaman bawah tabel | `button[aria-label='Go to next page']` | Berpindah ke halaman peringkat berikutnya secara otomatis. |

---

## 3. Hasil Pengujian Eksekusi End-to-End

Pengujian live scraping dijalankan dengan perintah CLI:
```bash
py -3.14 -m app.cli scrape --country ID --period yesterday --limit 5
```

### Hasil Log & Validasi:
1. **Inisialisasi Browser:** Google Chrome berhasil dibuka menggunakan `chrome_profile`.
2. **Validasi Sesi:** Halaman `https://www.kalodata.com/product` langsung dimuat tanpa hambatan Cloudflare Turnstile.
3. **Navigasi & Filter:**
   - Region switch ke `ID` terverifikasi.
   - Filter tanggal `Yesterday` dan kategori `Women's Bottoms` diterapkan.
   - Filter sumber pendapatan `Video` berhasil diaktifkan.
4. **Data Produk Terekstrak:** 5 produk terekstrak lengkap dengan Product ID unik, nama produk, dan link detail:
   - Rank 1: `[COD] KASUR TINGGI 25 CM INTHEBOX COMFY` (ID: `1731286968529029061`)
   - Rank 2: `POCO C81 Pro (4GB/128G) (4GB/64GB)` (ID: `1735248762346636825`)
   - Rank 3: `POCO F9 Series | POCO F9 Ultra` (ID: `1737690444488934937`)
   - Rank 4: `[ KINGMART 5.5] - KOPI KAPAL API 10 KARTON` (ID: `1731249355571692818`)
   - Rank 5: `MAYBELLINE Superstay Matte Ink Liquid` (ID: `1729382420060341472`)
5. **Ekspor Excel:** File `Product_ID_run-2026-10-19_data-2026-10-18_PARTIAL.xlsx` otomatis dibuat di `runtime/exports/2026/10/` berisi sheet `Data` dan sheet `Info`.
6. **Database Record:** Hasil tercatat di tabel `scrape_jobs` dan `export_files` dengan status `SUCCESS` / `PARTIAL`.

---

## 4. Status Server Dashboard Web
- **URL Dashboard:** `http://127.0.0.1:8081` (sedang berjalan aktif).
- **Akun Login:** `admin` / `admin123`.
- **Halaman Jadwal & Trigger:** `http://127.0.0.1:8081/jobs` (Tombol *⚡ Jalankan Scraper Kalodata Sekarang* siap digunakan kapan saja).
- **Halaman Hasil & Ekspor:** `http://127.0.0.1:8081/results` (File Excel langsung dapat diunduh dan dipratinjau).
- **Unit Tests:** 11/11 lolos (`py -3.14 -m pytest tests/ -v`).
