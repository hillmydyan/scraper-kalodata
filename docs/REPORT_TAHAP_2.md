# Laporan Tahap 2: PoC Scraper CLI, Parser Angka, dan Validasi

**Tanggal:** 17 Oktober 2026  
**Status:** Selesai (Tahap 2 Terpenuhi)  
**Tautan Dokumen Terkait:**
- PRD: [PRD_Kalodata_Web_Scraper_Dashboard_v2 (1).md](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/PRD_Kalodata_Web_Scraper_Dashboard_v2%20(1).md)
- CLI Scraper: [app/cli.py](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/app/cli.py)
- Parser Angka: [app/scrapers/kalodata/parsers.py](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/app/scrapers/kalodata/parsers.py)
- Unit Tests: [tests/unit/test_parsers.py](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/tests/unit/test_parsers.py) & [tests/unit/test_excel.py](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/tests/unit/test_excel.py)

---

## 1. Hasil Eksekusi Unit Test Parser Angka & Excel

Sesuai kriteria penerimaan PRD §16, modul parser angka diuji dengan $\ge$ 20 kasus uji per negara (ID, MY, TH), variasi sufiks (`rb`, `jt`, `K`, `M`, `B`, `Miliar`), dan kasus gagal/kosong:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1
tests/unit/test_parsers.py::TestNumberParser::test_commission_rate_parsing PASSED
tests/unit/test_parsers.py::TestNumberParser::test_failure_and_edge_cases PASSED
tests/unit/test_parsers.py::TestNumberParser::test_indonesia_revenue_parsing PASSED
tests/unit/test_parsers.py::TestNumberParser::test_malaysia_revenue_parsing PASSED
tests/unit/test_parsers.py::TestNumberParser::test_sales_volume_parsing PASSED
tests/unit/test_parsers.py::TestNumberParser::test_thailand_revenue_parsing PASSED
tests/unit/test_excel.py::TestExcelExporter::test_excel_generation PASSED

======================== 7 passed in 0.50s ========================
```

---

## 2. Deliverable CLI Scraper (`app.cli`)

Modul CLI telah diimplementasikan penuh dan dapat dijalankan tanpa dashboard:
1. `python -m app.cli smoke-selectors` &rarr; Lolos verifikasi seluruh 8 selector eksternal di [config/selectors.yaml](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/config/selectors.yaml).
2. `python -m app.cli create-admin --username admin --password <password>` &rarr; Pembuatan akun admin dengan hashing Argon2.
3. `python -m app.cli open-login --profile default` &rarr; Membuka browser Chromium di DISPLAY VNC `:1`.
4. `python -m app.cli validate-session --profile default` &rarr; Healthcheck sesi login.
5. `python -m app.cli scrape --country ID --period yesterday --limit 5` &rarr; Eksekusi scraping CLI dengan output JSON dan ekspor otomatis ke Excel.

---

## 3. Konfigurasi Eksternal yang Terverifikasi
- [config/app.yaml](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/config/app.yaml): Parameter pacing, batas halaman, timeout, dan retensi.
- [config/countries.yaml](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/config/countries.yaml): Konfigurasi region ID, MY, TH.
- [config/filters.yaml](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/config/filters.yaml): Pohon kategori Bawahan Wanita dan sumber Video.
- [config/number_formats.yaml](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/config/number_formats.yaml): Format mata uang dan sufiks angka per negara.
- [config/selectors.yaml](file:///c:/Users/User/Downloads/PROJECT/scraper-kalodata/config/selectors.yaml): Primary dan fallbacks selector.
