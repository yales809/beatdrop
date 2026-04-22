@echo off
title BeatDrop Pro - Auto Setup
color 0D
echo.
echo  =====================================================
echo   BEATDROP PRO - Auto Setup ^& Launcher
echo  =====================================================
echo.

:: Cek Python ada atau tidak
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python tidak ditemukan!
    echo.
    echo  Download Python di: https://www.python.org/downloads/
    echo  Centang "Add Python to PATH" saat install!
    echo.
    pause
    exit /b 1
)

echo  [OK] Python ditemukan
echo.

:: Install semua library yang dibutuhkan
echo  Installing Flask, yt-dlp, flask-sqlalchemy...
python -m pip install flask flask-sqlalchemy yt-dlp --upgrade -q
if errorlevel 1 (
    echo  [ERROR] Gagal install library!
    echo  Coba jalankan CMD sebagai Administrator.
    pause
    exit /b 1
)
echo  [OK] Library siap
echo.

:: Cek ffmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo  ffmpeg tidak ditemukan - menjalankan install.py...
    python install.py
) else (
    echo  [OK] ffmpeg sudah ada
)

echo.
echo  =====================================================
echo   Membuka browser otomatis...
echo  =====================================================
echo.

:: Buka browser setelah 2 detik
start /b cmd /c "timeout /t 2 >nul && start http://localhost:5000"

:: Jalankan app
python app.py

pause
