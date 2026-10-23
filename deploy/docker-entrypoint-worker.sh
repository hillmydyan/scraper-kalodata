#!/bin/bash
set -e

DISPLAY_NUM="${VNC_DISPLAY:-:1}"
RFB_PORT="${VNC_INTERNAL_PORT:-5901}"
GEOMETRY="${VNC_GEOMETRY:-1440x900x24}"
DISP_ID="${DISPLAY_NUM#:}"

echo "=================================================================="
echo " [KALODATA WORKER] Memulai Container Playwright + VNC Display"
echo " Display: $DISPLAY_NUM | Port VNC Internal: $RFB_PORT | Resolusi: $GEOMETRY"
echo "=================================================================="

# Bersihkan sisa lock X11 dan lock profil scraper jika ada restart
rm -f "/tmp/.X${DISP_ID}-lock" "/tmp/.X11-unix/X${DISP_ID}" 2>/dev/null || true
rm -f /app/runtime/locks/*.lock 2>/dev/null || true

# 1. Jalankan Xvfb virtual framebuffer
Xvfb $DISPLAY_NUM -screen 0 $GEOMETRY -ac +extension GLX +render -noreset &
XVFB_PID=$!
echo "[INFO] Xvfb virtual display aktif (PID: $XVFB_PID)"
sleep 1

# 2. Jalankan fluxbox window manager
DISPLAY=$DISPLAY_NUM fluxbox &
FLUXBOX_PID=$!
echo "[INFO] Fluxbox window manager aktif (PID: $FLUXBOX_PID)"

# 3. Jalankan x11vnc server (tanpa password atau gunakan password jika diset)
x11vnc -display $DISPLAY_NUM -rfbport $RFB_PORT -shared -forever -nopw &
VNC_PID=$!
echo "[INFO] x11vnc server aktif di port $RFB_PORT (PID: $VNC_PID)"

# Trap signal shutdown agar container berhenti dengan bersih
cleanup() {
    echo "[INFO] Menerima sinyal stop, menghentikan Celery worker dan VNC..."
    kill -TERM "$CELERY_PID" 2>/dev/null || true
    kill -TERM "$VNC_PID" "$FLUXBOX_PID" "$XVFB_PID" 2>/dev/null || true
    rm -f "/tmp/.X${DISP_ID}-lock" "/tmp/.X11-unix/X${DISP_ID}" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

export DISPLAY=$DISPLAY_NUM

# 4. Jalankan Celery worker
echo "=== Menjalankan Kalodata Celery Scraper Worker ==="
celery -A app.tasks.celery_app worker -c 1 -Q kalodata,celery --loglevel=INFO &
CELERY_PID=$!

wait $CELERY_PID
