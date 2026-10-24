#!/bin/bash
set -e

echo "=== Menunggu Database PostgreSQL & Redis siap ==="
python -c "
import time, os
from sqlalchemy import create_engine
db_url = os.getenv('DATABASE_URL')
for i in range(30):
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            print('PostgreSQL berhasil terhubung!')
            break
    except Exception as e:
        time.sleep(1)
"

# Pastikan schema database terinisialisasi dan akun admin tersedia
python -c "from app.models import init_db; init_db()" || true
python -m app.cli create-admin --username admin --password admin || true
python -m app.cli set-account --email "pohon.cemara0706@gmail.com" --password "wisnu6696!" || true

echo "=== Menjalankan Web Dashboard Gunicorn di port 8081 ==="
exec gunicorn --bind 0.0.0.0:8081 --workers 2 --timeout 120 "app:create_app()"
