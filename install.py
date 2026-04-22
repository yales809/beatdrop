"""
BeatDrop Pro — Auto Installer
Jalankan sekali: python install.py
"""
import subprocess, sys, os, platform, urllib.request, zipfile, shutil

def run(cmd):
    print(f"  >> {' '.join(cmd)}")
    subprocess.check_call(cmd)

def banner(msg):
    print(f"\n{'='*55}")
    print(f"  {msg}")
    print(f"{'='*55}")

banner("🎧 BeatDrop Pro — Auto Installer")

# ── 1. Install Python packages ────────────────────────────────
banner("📦 Step 1: Install Python packages...")
packages = ["flask", "flask-sqlalchemy", "yt-dlp"]
for pkg in packages:
    try:
        run([sys.executable, "-m", "pip", "install", pkg, "--upgrade", "-q"])
        print(f"  ✅ {pkg} OK")
    except Exception as e:
        print(f"  ❌ Gagal install {pkg}: {e}")

# ── 2. Check / Install ffmpeg ────────────────────────────────
banner("🎬 Step 2: Cek ffmpeg...")

def ffmpeg_ok():
    try:
        subprocess.check_output(["ffmpeg", "-version"], stderr=subprocess.STDOUT)
        return True
    except:
        return False

if ffmpeg_ok():
    print("  ✅ ffmpeg sudah terinstall!")
else:
    print("  ⚠️  ffmpeg tidak ditemukan. Mencoba install otomatis...")
    system = platform.system()

    if system == "Windows":
        # Download ffmpeg pre-built untuk Windows
        ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        ffmpeg_zip = "ffmpeg_win.zip"
        ffmpeg_dir = os.path.join(os.path.dirname(__file__), "ffmpeg_win")
        print("  ⬇️  Download ffmpeg untuk Windows...")
        try:
            urllib.request.urlretrieve(ffmpeg_url, ffmpeg_zip)
            with zipfile.ZipFile(ffmpeg_zip, 'r') as z:
                z.extractall(ffmpeg_dir)
            os.remove(ffmpeg_zip)
            # Cari ffmpeg.exe
            for root, dirs, files in os.walk(ffmpeg_dir):
                if "ffmpeg.exe" in files:
                    ffmpeg_path = os.path.join(root, "ffmpeg.exe")
                    # Copy ke folder project agar mudah
                    shutil.copy(ffmpeg_path, os.path.dirname(__file__))
                    print(f"  ✅ ffmpeg.exe disalin ke folder project!")
                    break
            # Tambahkan path ke environment sesi ini
            os.environ["PATH"] = os.path.dirname(__file__) + os.pathsep + os.environ.get("PATH","")
        except Exception as e:
            print(f"  ❌ Gagal download ffmpeg: {e}")
            print("  👉 Download manual: https://www.gyan.dev/ffmpeg/builds/")
            print("     Ekstrak & taruh ffmpeg.exe di folder BeatDrop ini.")

    elif system == "Darwin":  # macOS
        print("  ℹ️  Install ffmpeg via Homebrew...")
        try:
            run(["brew", "install", "ffmpeg"])
            print("  ✅ ffmpeg terinstall via Homebrew!")
        except:
            print("  ❌ Homebrew tidak ada. Install manual:")
            print("     brew install ffmpeg")
            print("     atau download: https://evermeet.cx/ffmpeg/")

    elif system == "Linux":
        print("  ℹ️  Install ffmpeg via apt...")
        try:
            run(["sudo", "apt-get", "install", "-y", "ffmpeg"])
            print("  ✅ ffmpeg terinstall!")
        except:
            try:
                run(["sudo", "yum", "install", "-y", "ffmpeg"])
                print("  ✅ ffmpeg terinstall via yum!")
            except:
                print("  ❌ Gagal auto-install. Coba manual:")
                print("     sudo apt install ffmpeg")

    # Re-check
    if ffmpeg_ok():
        print("  ✅ ffmpeg siap digunakan!")
    else:
        print("\n  ⚠️  ffmpeg belum terdeteksi.")
        print("  ℹ️  Download MP3 butuh ffmpeg. Download video (MP4) tetap bisa.")

# ── 3. Buat folder downloads ─────────────────────────────────
os.makedirs(os.path.join(os.path.dirname(__file__), "downloads"), exist_ok=True)
print("\n  ✅ Folder downloads siap")

# ── 4. Selesai ───────────────────────────────────────────────
banner("🚀 Instalasi selesai! Jalankan:")
print("  python app.py\n")
print("  Lalu buka browser: http://localhost:5000\n")
