# Catatan Observasi UI Kalodata (Draft Tahap 1–2)

Dokumen ini mencatat temuan nyata dari UI Kalodata (kalodata.com) sebelum dimasukkan ke dalam konfigurasi kode. Semua nilai di sini akan diverifikasi langsung di browser.

---

## 1. Bahasa Antarmuka (UI Language)
* **Target Bahasa:** English (`en`)
* **Lokasi Pemilih Bahasa:** (Akan diverifikasi)
* **Selector Pemilih Bahasa:** (Akan diisi di Tahap 2)

---

## 2. Pemilih Wilayah / Region (ID, MY, TH)
* **Label Region di UI:**
  - Indonesia: `Indonesia` / `ID`
  - Malaysia: `Malaysia` / `MY`
  - Thailand: `Thailand` / `TH`
* **Indikator Region Aktif:** (Label di header / mata uang tabel / URL parameter)
* **Verifikasi Switch Region:** (Memastikan pergantian region tidak memerlukan relogin)

---

## 3. Rentang Waktu / Date Picker
* **Pilihan Periode:** Eksplisit tanggal kemarin (bukan preset tanpa label tanggal)
* **Format Tanggal di UI:** (mis. `YYYY-MM-DD` atau `DD/MM/YYYY`)
* **Zona Waktu Kalodata:** (Perlu diobservasi: apakah UTC, UTC+8 / Beijing Time, atau UTC+7 / WIB)
* **Readiness Data Kemarin (§8.4):** Jam ketersediaan data kemarin lengkap di Kalodata.

---

## 4. Kategori Produk: "Bawahan Wanita"
* **Pohon Kategori Indonesia:** mis. *Womenswear & Underwear* $\rightarrow$ *Women's Bottoms* / setara
* **Pohon Kategori Malaysia:** (Akan diverifikasi)
* **Pohon Kategori Thailand:** (Akan diverifikasi)
* **Selector Dropdown / Cascader:** (Akan dicatat di `config/selectors.yaml`)

---

## 5. Sumber Pendapatan: Video
* **Apakah ada filter "Revenue Source = Video" di halaman Product List?**
  - Jika YA: Gunakan langsung (`product_filter`).
  - Jika TIDAK: Ikuti fallback §6.4 (Buka detail produk $\rightarrow$ cek breakdown Video).

---

## 6. Format Angka & Simbol Mata Uang
* **Indonesia (ID):** Mata uang `Rp`, contoh singkatan: `Rp 1,2jt`, `1.5M`, `12K`.
* **Malaysia (MY):** Mata uang `RM`, contoh singkatan: `RM 12.5K`, `RM 1.2M`.
* **Thailand (TH):** Mata uang `฿`, contoh singkatan: `฿12K`, `฿1.2M`.
* **Desimal vs Pemisah Ribuan:** Titik vs koma.

---

## 7. Pemilihan 1 Video Terbaik per Produk (§6.7)
* Tab video terkait di halaman detail produk.
* Ketersediaan sorting berdasarkan pendapatan (GMV) untuk periode kemarin.
* Link video TikTok asli (`tiktok.com/@.../video/...`) vs URL internal Kalodata.
