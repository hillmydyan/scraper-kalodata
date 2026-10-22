#!/usr/bin/env bash
# Script to launch virtual X display and VNC server for Kalodata scraper
set -e

DISPLAY_NUM="${VNC_DISPLAY:-:2}"
RFB_PORT="${VNC_PORT:-5902}"
GEOMETRY="1440x900x24"
DISP_ID="${DISPLAY_NUM#:}"

echo "=== Memulai Virtual Display ($DISPLAY_NUM) & VNC Server (Port $RFB_PORT) ==="

# Bersihkan sisa lock X11 jika ada crash sebelumnya
rm -f "/tmp/.X${DISP_ID}-lock" "/tmp/.X11-unix/X${DISP_ID}" 2>/dev/null || true

# Jalankan Xvfb virtual framebuffer
Xvfb $DISPLAY_NUM -screen 0 $GEOMETRY -ac +extension GLX +render -noreset &
XVFB_PID=$!
echo "[INFO] Xvfb berjalan (PID: $XVFB_PID)"

# Tunggu 1 detik hingga X server siap
sleep 1

# Jalankan window manager ringan agar browser bisa diatur ukurannya
DISPLAY=$DISPLAY_NUM fluxbox &
FLUXBOX_PID=$!
echo "[INFO] Fluxbox berjalan (PID: $FLUXBOX_PID)"

# Trap signal agar saat service dihentikan, seluruh subprocess ikut mati
cleanup() {
    echo "[INFO] Menghentikan VNC dan virtual display..."
    kill -TERM "$XVFB_PID" "$FLUXBOX_PID" "$VNC_PID" 2>/dev/null || true
    rm -f "/tmp/.X${DISP_ID}-lock" "/tmp/.X11-unix/X${DISP_ID}" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Jalankan x11vnc server
# Catatan: Akses lokal atau SSH Tunnel sangat disarankan untuk keamanan
x11vnc -display $DISPLAY_NUM -rfbport $RFB_PORT -shared -forever -nopw &
VNC_PID=$!
echo "[INFO] x11vnc berjalan di port $RFB_PORT (PID: $VNC_PID)"

wait $VNC_PID
