# PROMPT AI AGENT — REDESIGN DASHBOARD KURMA SCRAPER

## 1. Role

Kamu adalah Senior Frontend Engineer sekaligus UI/UX Designer yang berpengalaman membangun dashboard admin modern, responsif, dan production-ready.

Tugasmu adalah melakukan redesign UI/UX pada project **Kurma Scraper — Kalodata Intel** yang sudah ada, dengan tetap mempertahankan seluruh fungsi scraping, backend, database, autentikasi, scheduler, dan sistem ekspor yang telah berjalan.

Jangan hanya memberikan saran atau mockup. **Periksa project yang ada, implementasikan redesign langsung pada kode, lalu jalankan pengujian.**

## 2. Referensi Desain

Gunakan screenshot dashboard yang diberikan sebagai referensi struktur informasi dan screenshot redesign sebagai referensi visual.

Arah desain:
- Modern, premium, minimalis, dan profesional.
- Dominasi warna hijau tua, emerald, putih, dan abu-abu netral.
- Nuansa glassmorphism yang halus, bukan berlebihan.
- Layout dashboard luas dengan whitespace yang terkontrol.
- Card dengan rounded corners, border tipis, dan shadow lembut.
- Tipografi jelas dan hierarki informasi kuat.
- Tampilan cocok untuk aplikasi internal perusahaan.
- Hindari desain yang terlalu ramai, terlalu banyak warna, atau terlalu banyak dekorasi.

Branding:
- Nama aplikasi: **Kurma Scraper**
- Subjudul: **KALODATA INTEL**
- Identitas visual menggunakan warna hijau yang konsisten dengan branding Kurma Group.
- Pertahankan logo yang sudah tersedia jika ada. Jangan mengganti logo asli dengan logo generik.

## 3. Aturan Wajib: Jangan Gunakan Icon Library

**Jangan gunakan icon library atau paket ikon apa pun.**

Dilarang menggunakan:
- Lucide React
- React Icons
- Font Awesome
- Heroicons
- Bootstrap Icons
- Material Icons
- Emoji sebagai pengganti ikon UI
- Karakter Unicode sebagai ikon dekoratif

Jika membutuhkan ikon, buat menggunakan **inline SVG** langsung di dalam komponen.

Contoh:

```jsx
function DashboardIcon({ size = 20, color = "currentColor" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M3 10.5L12 3L21 10.5V20H3V10.5Z"
        stroke={color}
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M9 20V13H15V20"
        stroke={color}
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
```

Ketentuan SVG:
- Gunakan `stroke` untuk ikon outline.
- Konsisten dengan `strokeWidth` sekitar 1.6–1.9.
- Gunakan `currentColor` agar warna dapat mengikuti tema.
- Ukuran ikon navigasi sekitar 20–22 px.
- Ukuran ikon kecil sekitar 16–18 px.
- Ukuran ikon statistik sekitar 22–26 px.
- Gunakan SVG sederhana, bersih, dan konsisten.
- Gunakan `aria-hidden="true"` untuk ikon dekoratif.
- Hindari SVG yang terlalu kompleks dan tidak diperlukan.

Buat komponen reusable untuk ikon SVG, misalnya `SvgIcon`, atau komponen khusus untuk setiap ikon. Jangan membuat SVG duplikat jika bentuknya sama.

Jika sebuah elemen dapat dipahami tanpa ikon, **lebih baik gunakan teks, angka, garis, atau indikator status sederhana**.

## 4. Tahap Pertama: Audit Project

Sebelum mengubah kode:

1. Periksa struktur folder dan entry point aplikasi.
2. Identifikasi framework frontend dan backend yang digunakan.
3. Periksa package manager dan dependency yang sudah terpasang.
4. Identifikasi seluruh halaman, komponen, route, API, dan layout.
5. Pelajari bagaimana dashboard mengambil data status scraping.
6. Periksa sistem autentikasi, session, database, Redis Queue, browser engine, scheduler, dan ekspor.
7. Identifikasi CSS, template, dan komponen yang sudah ada.
8. Tentukan bagian yang perlu diubah dan bagian yang wajib dipertahankan.

Jangan mengganti framework atau membangun ulang backend tanpa alasan teknis yang kuat.

Gunakan stack dan arsitektur project yang sudah tersedia.

## 5. Redesign Layout Utama

### A. Sidebar

Buat sidebar vertikal dengan warna hijau tua, misalnya `#073B32` atau `#0B3D32`.

Sidebar berisi:

**Brand**
- Logo Kurma.
- Nama Kurma Scraper.
- Label KALODATA INTEL.

**Main Menu**
- Dashboard
- Hasil & Ekspor
- Smart Analytics dengan label AI

**Admin Tools**
- Jadwal & Trigger
- Manajemen User
- Akun & Sesi

**User Profile**
- Avatar inisial pengguna.
- Nama pengguna.
- Role pengguna.
- Tombol logout.

Ketentuan:
- Item aktif menggunakan latar hijau yang sedikit lebih terang, border halus, dan teks putih.
- Item tidak aktif menggunakan teks putih dengan opacity yang sesuai.
- Sidebar harus memiliki jarak antargrup yang konsisten.
- Profil pengguna berada di bagian bawah sidebar.
- Sidebar dapat dibuat collapsible jika sesuai dengan arsitektur project.
- Navigasi harus tetap berfungsi. Jangan sekadar mengubah tampilannya.

Gunakan inline SVG untuk ikon navigasi jika ikon diperlukan.

### B. Top Navigation

Buat header yang bersih dengan elemen:
- Status sistem Online/Offline.
- Tanggal dan waktu lokal WIB.
- Informasi pengguna yang sedang login.
- Dropdown profil jika memang sudah tersedia atau dibutuhkan.

Gunakan background hijau tua atau variasi gelap yang menyatu dengan sidebar.

Tanggal dan waktu harus berasal dari sistem yang benar, bukan teks statis.

Status sistem harus berasal dari status backend atau health check yang sebenarnya.

### C. Main Content

Gunakan background putih atau off-white, misalnya `#F7FAF8`.

Atur padding konten agar proporsional dan tidak terlalu lebar jaraknya.

Pada bagian atas tampilkan:
- Sapaan atau eyebrow text: `SELAMAT DATANG DI`
- Judul: `Kurma Scraper`
- Deskripsi: `Pantau status antrian scraping, kesehatan pipeline background, dan sesi akun Kalodata secara real-time.`
- Indikator `Monitoring Aktif (WIB)`.

Buat hero section yang elegan dengan gradasi hijau sangat lembut, rounded corners, dan dekorasi abstrak yang minimal.

Hindari ilustrasi besar yang mengganggu informasi utama.

## 6. System Overview

Buat panel ringkasan sistem dengan enam informasi berikut:

1. **Database**
   - Status ONLINE/OFFLINE.
2. **Redis Queue**
   - Status ONLINE/OFFLINE.
3. **Browser Engine**
   - Nama browser aktif, misalnya Google Chrome.
4. **Jadwal Otomatis**
   - Jadwal scraping berikutnya.
5. **Penyimpanan Bebas**
   - Kapasitas penyimpanan yang tersedia.
6. **Total File Hasil**
   - Jumlah file hasil scraping.

Layout:
- Gunakan card horizontal dengan enam bagian.
- Pada desktop, usahakan seluruh informasi dapat dilihat dalam satu baris jika ruang mencukupi.
- Pada layar lebih kecil, susun ulang menjadi beberapa kolom atau grid.
- Gunakan divider tipis antarbagian.
- Angka dan status harus lebih menonjol daripada label.
- Status online gunakan hijau.
- Status offline atau error gunakan merah.
- Status peringatan gunakan amber.

Data harus terhubung dengan sumber data yang sebenarnya. Jangan mengarang angka atau membuat status palsu demi tampilan.

## 7. Monitoring Scraping per Wilayah

Buat bagian berjudul:

**Status Scraping Terkini per Wilayah**

Tambahkan tautan teks:
`Unduh Hasil di Halaman Hasil & Ekspor →`

Tampilkan status setiap wilayah dalam card terpisah dengan desain konsisten.

Contoh data yang perlu dapat ditampilkan:

### Indonesia

- Kode wilayah: ID
- Nama wilayah: Indonesia
- Status: SUCCESS
- Modul scrape: Kreator
- Stage: SCRAPING_CREATORS
- Periode data: 2026-10-18
- Waktu mulai: 19 Okt 2026, 15:16 WIB
- Data ditemukan: 2 item
- Data disimpan: 6 item

### Malaysia

- Kode wilayah: MY
- Nama wilayah: Malaysia
- Status: FAILED
- Modul scrape: Produk
- Stage: NAVIGATING_REGION
- Periode data: 2026-10-18
- Waktu mulai: 19 Okt 2026, 09:05 WIB
- Data ditemukan: 0 item
- Data disimpan: 0 item

**Catatan:** Angka di atas hanya data referensi desain. Implementasi final wajib menggunakan data aktual dari backend.

Setiap card harus berisi:

**Header**
- Badge atau blok kode negara.
- Nama wilayah.
- Status scraping.

**Detail**
- Modul scraping.
- Tahapan proses.
- Periode data.
- Waktu mulai.
- Jumlah data ditemukan.
- Jumlah data disimpan.

**Footer**
- Aksi `Lihat Detail Job →`
- Aksi `Buka Berkas Hasil →`

Ketentuan desain:
- SUCCESS menggunakan badge hijau muda dengan teks hijau tua.
- FAILED menggunakan badge merah muda dengan teks merah tua.
- RUNNING menggunakan indikator biru atau emerald.
- PENDING menggunakan warna netral.
- Tahapan proses tampil sebagai label kecil dengan background netral.
- Angka hasil ditemukan dan disimpan dapat menggunakan font weight lebih tebal.
- Gunakan divider tipis untuk memisahkan header, detail, dan footer.
- Seluruh card harus konsisten dalam ukuran, spacing, dan alignment.

Tombol dan tautan harus tetap menjalankan fungsi yang sudah ada. Jangan membuat aksi palsu.

## 8. Design System

Gunakan CSS variables agar desain mudah dipelihara.

Contoh:

```css
:root {
  --color-primary: #0B3D32;
  --color-primary-hover: #14532D;
  --color-primary-soft: #E8F5EC;

  --color-background: #F7FAF8;
  --color-surface: #FFFFFF;
  --color-text: #17221F;
  --color-text-muted: #718078;

  --color-border: #E2EBE5;

  --color-success: #15803D;
  --color-success-bg: #DCFCE7;

  --color-danger: #DC2626;
  --color-danger-bg: #FEE2E2;

  --color-warning: #B45309;
  --color-warning-bg: #FEF3C7;

  --radius-sm: 8px;
  --radius-md: 14px;
  --radius-lg: 20px;

  --shadow-card:
    0 4px 18px rgba(15, 55, 42, 0.05);
}
```

Nilai di atas merupakan titik awal dan boleh disesuaikan secara konsisten.

Gunakan:
- Font sans-serif modern.
- Ukuran heading yang jelas.
- Body text sekitar 14–16 px.
- Label pendukung sekitar 12–14 px.
- Jarak berbasis skala konsisten.
- Border tipis dan shadow ringan.
- Hover transition sekitar 150–200 ms.

Hindari:
- Gradient berlebihan.
- Shadow hitam yang terlalu kuat.
- Border pada hampir setiap elemen.
- Font terlalu kecil.
- Animasi yang mengganggu.
- Terlalu banyak card bersarang.
- Terlalu banyak pill atau badge yang tidak diperlukan.

## 9. Responsivitas

Pastikan desain berjalan baik pada:
- Desktop 1440 px.
- Laptop 1366 px.
- Tablet.
- Mobile.

Ketentuan:
- Sidebar dapat berubah menjadi drawer pada layar kecil.
- Kartu monitoring menyesuaikan jumlah kolom.
- Tabel tetap mudah digunakan pada layar kecil.
- Tidak boleh ada horizontal overflow pada keseluruhan halaman.
- Tombol dan elemen interaktif memiliki area klik yang memadai.
- Layout tetap rapi saat teks, jumlah file, atau nama wilayah lebih panjang.
- Pastikan halaman tetap dapat digunakan ketika data kosong atau API sedang mengalami error.

## 10. UX dan State

Implementasikan state UI yang sesuai dengan kondisi aplikasi:

- Loading.
- Data tersedia.
- Data kosong.
- Gagal memuat data.
- Sistem offline.
- Scraping berjalan.
- Scraping berhasil.
- Scraping gagal.

Gunakan skeleton loading atau indikator loading yang sederhana.

Jika API gagal:
- Tampilkan pesan yang jelas.
- Sediakan tombol coba lagi jika sesuai.
- Jangan menampilkan data dummy seolah-olah merupakan data real-time.
- Jangan menyembunyikan error backend yang penting bagi administrator.

Jika sudah ada mekanisme polling atau WebSocket, pertahankan dan integrasikan dengan desain baru. Jangan menambahkan polling agresif yang membebani backend.

## 11. Pertahankan Seluruh Fungsi Lama

Redesign hanya boleh mengubah presentasi dan UX kecuali ada kebutuhan teknis yang jelas.

Jangan merusak:
- Login dan logout.
- Session dan autentikasi.
- Role administrator dan hak akses.
- Koneksi database.
- Redis Queue.
- Proses scraping Playwright.
- Pengelolaan akun Kalodata.
- Pengelolaan sesi browser.
- Scheduler otomatis pukul 01.00 WIB.
- Trigger manual.
- Pemilihan wilayah.
- Modul Kreator dan Produk.
- Detail job.
- Riwayat scraping.
- Hasil dan ekspor Excel.
- Fitur Smart Analytics.
- API dan routing yang sudah ada.

Jangan mengubah logika scraping atau filter data hanya untuk mendukung redesign.

Jangan menghapus fitur lama yang tidak terlihat pada screenshot. Semua halaman lain tetap harus berfungsi dan mengikuti design system baru secara bertahap.

## 12. Struktur Komponen

Sesuaikan dengan framework yang ditemukan saat audit.

Jika menggunakan React, usahakan komponen modular seperti:

- `AppLayout`
- `Sidebar`
- `Topbar`
- `PageHeader`
- `SystemOverview`
- `SystemMetric`
- `RegionStatusSection`
- `RegionStatusCard`
- `StatusBadge`
- `StageBadge`
- `UserProfile`
- `SvgIcon`

Nama komponen boleh disesuaikan dengan struktur project.

Jangan membuat satu file komponen raksasa yang mencampur seluruh layout, fetching data, dan business logic.

Pisahkan tanggung jawab UI, state, dan integrasi API sesuai pola project yang sudah ada.

## 13. Accessibility dan Kualitas Kode

- Gunakan semantic HTML.
- Pastikan kontras teks memadai.
- Jangan mengandalkan warna saja untuk membedakan status; sertakan label teks.
- Tambahkan accessible name pada tombol yang hanya berisi SVG.
- Gunakan `button` untuk aksi dan `a` untuk navigasi yang sesuai.
- Jangan menggunakan elemen non-interaktif sebagai tombol.
- Hindari duplikasi CSS.
- Hindari dependency baru yang tidak diperlukan.
- Jangan menambahkan icon package.
- Jangan hardcode status dinamis.
- Jangan menghapus konfigurasi atau environment variable yang sudah ada.

## 14. Tahapan Implementasi

Kerjakan secara berurutan:

1. Audit struktur project.
2. Identifikasi framework dan komponen existing.
3. Buat rencana perubahan singkat.
4. Implementasikan design system.
5. Redesign sidebar dan topbar.
6. Redesign dashboard dan system overview.
7. Redesign kartu monitoring per wilayah.
8. Integrasikan kembali data backend.
9. Terapkan styling konsisten pada halaman lain.
10. Pastikan semua navigasi dan aksi berfungsi.
11. Jalankan lint, test, dan build sesuai toolchain project.
12. Perbaiki error yang ditemukan.
13. Verifikasi tampilan desktop dan responsivitas.

Jangan berhenti setelah membuat rencana. Lanjutkan sampai implementasi dan pengujian selesai.

## 15. Acceptance Criteria

Pekerjaan dinyatakan selesai jika:

- [ ] Dashboard memiliki tampilan modern, bersih, dan konsisten.
- [ ] Warna utama hijau tua, emerald, putih, dan abu-abu netral.
- [ ] Tidak ada penggunaan icon library atau emoji untuk ikon UI.
- [ ] Seluruh ikon yang diperlukan menggunakan inline SVG.
- [ ] Sidebar dan topbar berfungsi.
- [ ] Ringkasan kesehatan sistem menggunakan data aktual.
- [ ] Monitoring wilayah mengambil data aktual backend.
- [ ] Badge status mencerminkan status scraping sebenarnya.
- [ ] Detail job dan hasil ekspor tetap dapat diakses.
- [ ] Semua halaman lama tetap berfungsi.
- [ ] Login, role, dan hak akses tidak rusak.
- [ ] Scheduler pukul 01.00 WIB tetap berjalan sesuai implementasi lama.
- [ ] Tidak ada data dummy yang ditampilkan sebagai data aktual.
- [ ] Layout responsif tanpa overflow yang tidak diinginkan.
- [ ] Tidak ada error build atau lint baru yang belum ditangani.
- [ ] Tidak ada dependency ikon baru.

## 16. Laporan Akhir

Setelah selesai, laporkan:

1. Framework dan struktur project yang ditemukan.
2. File yang dibuat atau diubah.
3. Perubahan UI/UX yang berhasil diimplementasikan.
4. Komponen SVG yang dibuat.
5. Integrasi backend yang dipertahankan.
6. Hasil lint, test, dan build.
7. Kendala yang masih tersisa.
8. Cara menjalankan dan memverifikasi hasil redesign.

**Prioritas utama:** desain premium, keterbacaan data monitoring, penggunaan inline SVG tanpa icon library, responsivitas, dan tidak merusak fungsi scraper yang sudah berjalan.