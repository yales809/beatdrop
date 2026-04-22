#!/bin/bash
echo ""
echo "====================================================="
echo "  BEATDROP PRO - Auto Setup & Launcher"
echo "====================================================="
echo ""

# Cek Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "[ERROR] Python tidak ditemukan!"
    echo "Install: sudo apt install python3  (Linux)"
    echo "         brew install python3      (Mac)"
    exit 1
fi
PY=$(command -v python3 || command -v python)
echo "[OK] Python: $($PY --version)"

# Install libraries
echo ""
echo "Installing Flask, yt-dlp, flask-sqlalchemy..."
$PY -m pip install flask flask-sqlalchemy yt-dlp --upgrade -q
echo "[OK] Library siap"

# Cek ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo ""
    echo "ffmpeg tidak ada - menjalankan install.py..."
    $PY install.py
else
    echo "[OK] ffmpeg sudah ada"
fi

echo ""
echo "Membuka http://localhost:5000 ..."

# Buka browser
sleep 2 && (
    if command -v xdg-open &>/dev/null; then xdg-open http://localhost:5000
    elif command -v open &>/dev/null; then open http://localhost:5000
    fi
) &

$PY app.py
