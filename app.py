"""
BeatDrop Pro 2026 - Flask Backend
"""
import sys, os, io, shutil, threading, uuid, re, time, platform
import subprocess as sp

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def _ensure(pkg, imp=None):
    try:
        __import__(imp or pkg)
    except ImportError:
        print("  Installing {}...".format(pkg), flush=True)
        sp.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                      stdout=sp.DEVNULL, stderr=sp.DEVNULL)

_ensure("flask")
_ensure("flask_sqlalchemy", "flask_sqlalchemy")
_ensure("yt_dlp")

from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import yt_dlp

BASE   = os.path.dirname(os.path.abspath(__file__))
DL_DIR = '/tmp/downloads'
DB_DIR = '/tmp/instance'
os.makedirs(DL_DIR, exist_ok=True)
os.makedirs(DB_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(DB_DIR, "beatdrop.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ── ffmpeg finder ──────────────────────────────────────────────────────────────
def _find_ffmpeg():
    # ✅ Cek /tmp untuk Vercel environment
    for path in ['/tmp/ffmpeg', '/tmp/bin/ffmpeg', '/usr/local/bin/ffmpeg']:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    
    p = shutil.which("ffmpeg")
    if p:
        return p
    for name in ("ffmpeg.exe", "ffmpeg"):
        p = os.path.join(BASE, name)
        if os.path.exists(p):
            return p
    for root, _d, files in os.walk(os.path.join(BASE, "ffmpeg_win")):
        for f in files:
            if f.lower() in ("ffmpeg.exe", "ffmpeg"):
                return os.path.join(root, f)
    local_app = os.environ.get("LOCALAPPDATA", "")
    winget = os.path.join(local_app, "Microsoft", "WinGet", "Packages")
    if os.path.exists(winget):
        for folder in os.listdir(winget):
            if "ffmpeg" in folder.lower() or "gyan" in folder.lower():
                for root, _d, files in os.walk(os.path.join(winget, folder)):
                    for f in files:
                        if f.lower() == "ffmpeg.exe":
                            return os.path.join(root, f)
    for pf in (os.environ.get("ProgramFiles",""), os.environ.get("ProgramFiles(x86)",""), os.environ.get("ProgramW6432","")):
        for sub in ("ffmpeg", os.path.join("ffmpeg", "bin")):
            p = os.path.join(pf, sub, "ffmpeg.exe")
            if os.path.exists(p):
                return p
    return None

FFMPEG  = _find_ffmpeg()
HAVE_FF = FFMPEG is not None
FF_DIR  = os.path.dirname(FFMPEG) if HAVE_FF else None

cancelled_jobs = set()
download_queue = []
queue_lock     = threading.Lock()
active_count   = 0
MAX_CONCURRENT = 2

def _auto_update():
    try:
        sp.check_call([sys.executable, "-m", "pip", "install", "yt-dlp", "--upgrade", "-q"],
                      stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    except Exception:
        pass

threading.Thread(target=_auto_update, daemon=True).start()

# ── DB model ───────────────────────────────────────────────────────────────────
class Download(db.Model):
    id            = db.Column(db.Integer,     primary_key=True)
    uid           = db.Column(db.String(36),  unique=True, nullable=False)
    url           = db.Column(db.Text,        nullable=False)
    title         = db.Column(db.String(500), default="Unknown")
    custom_name   = db.Column(db.String(500), default="")
    thumbnail     = db.Column(db.Text,        default="")
    duration      = db.Column(db.String(20),  default="N/A")
    uploader      = db.Column(db.String(200), default="N/A")
    format_type   = db.Column(db.String(20),  nullable=False)
    audio_quality = db.Column(db.String(10),  default="320")
    status        = db.Column(db.String(20),  default="pending")
    progress      = db.Column(db.Float,       default=0.0)
    speed         = db.Column(db.String(30),  default="")
    eta           = db.Column(db.String(20),  default="")
    filename      = db.Column(db.String(500), default="")
    filesize      = db.Column(db.String(50),  default="N/A")
    error_msg     = db.Column(db.Text,        default="")
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow)
    completed_at  = db.Column(db.DateTime,    nullable=True)

    def to_dict(self):
        return dict(
            id=self.id, uid=self.uid, url=self.url,
            title=self.title, custom_name=(self.custom_name or ""),
            thumbnail=self.thumbnail, duration=self.duration, uploader=self.uploader,
            format_type=self.format_type, audio_quality=self.audio_quality,
            status=self.status, progress=round(self.progress, 1),
            speed=(self.speed or ""), eta=(self.eta or ""),
            filename=self.filename, filesize=self.filesize, error_msg=(self.error_msg or ""),
            created_at=self.created_at.strftime("%d %b %Y %H:%M") if self.created_at else "",
            completed_at=self.completed_at.strftime("%d %b %Y %H:%M") if self.completed_at else "",
        )

with app.app_context():
    db.create_all()
    from sqlalchemy import text as _T
    for _s in [
        "ALTER TABLE download ADD COLUMN custom_name VARCHAR(500) DEFAULT ''",
        "ALTER TABLE download ADD COLUMN speed VARCHAR(30) DEFAULT ''",
        "ALTER TABLE download ADD COLUMN eta VARCHAR(20) DEFAULT ''",
    ]:
        try:
            with db.engine.connect() as _c:
                _c.execute(_T(_s))
                _c.commit()
        except Exception:
            pass

# ── helpers ────────────────────────────────────────────────────────────────────
def clean_url(url):
    url = url.strip()
    m = re.match(r"https?://(?:www\.)?youtu\.be/([A-Za-z0-9_\-]{11})", url)
    if m:
        return "https://www.youtube.com/watch?v=" + m.group(1)
    if "youtube.com" in url:
        v = re.search(r"[?&]v=([A-Za-z0-9_\-]{11})", url)
        if v:
            return "https://www.youtube.com/watch?v=" + v.group(1)
    return url

def extract_vid(url):
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_\-]{11})", url)
    return m.group(1) if m else None

def friendly(e):
    s = str(e).lower()
    if "sign in" in s or "age" in s:  return "Video memerlukan login atau dibatasi usia."
    if "private" in s:                return "Video bersifat privat."
    if "unavailable" in s or "not available" in s: return "Video tidak tersedia atau sudah dihapus."
    if "geo" in s or "country" in s:  return "Video diblokir di negara Anda."
    if "copyright" in s:              return "Video diblokir karena hak cipta."
    if "ffmpeg" in s:                 return "ffmpeg tidak ditemukan. Jalankan install.py dulu."
    if "resolve" in s or "connect" in s: return "Gagal terhubung ke internet."
    return str(e)[:300]

def disk_free_gb():
    try:
        _, _, free = shutil.disk_usage(DL_DIR)
        return free / (1024 ** 3)
    except Exception:
        return 99.0

def fmt_eta(secs):
    if secs is None: return ""
    secs = int(secs)
    return "{}d".format(secs) if secs < 60 else "{}m{}d".format(secs // 60, str(secs % 60).zfill(2))

def fmt_speed(bps):
    if bps is None: return ""
    if bps >= 1048576: return "{:.1f} MB/s".format(bps / 1048576)
    if bps >= 1024:    return "{:.0f} KB/s".format(bps / 1024)
    return "{:.0f} B/s".format(bps)

def _base():
    opts = dict(
        quiet=True, no_warnings=True, nocheckcertificate=True, geo_bypass=True,
        socket_timeout=60, retries=10, fragment_retries=10,
        extractor_args={
            "youtube": {
                "player_client": ["web", "android"],
                "skip": ["dash", "hls"],
            }
        },
        http_headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        },
    )
    if HAVE_FF:
        opts["ffmpeg_location"] = FF_DIR
    return opts

def _hook(uid):
    def h(d):
        if uid in cancelled_jobs:
            raise Exception("Download dibatalkan oleh pengguna.")
        with app.app_context():
            row = Download.query.filter_by(uid=uid).first()
            if not row: return
            if d["status"] == "downloading":
                tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                dl  = d.get("downloaded_bytes", 0)
                if tot > 0:
                    row.progress = round(dl / tot * 100, 1)
                else:
                    try: row.progress = float((d.get("_percent_str") or "0%").strip().rstrip("%"))
                    except ValueError: row.progress = 0.0
                row.speed = fmt_speed(d.get("speed"))
                row.eta   = fmt_eta(d.get("eta"))
                row.status = "downloading"
                db.session.commit()
            elif d["status"] == "finished":
                row.progress = 99
                row.status = "processing"
                row.speed = ""
                row.eta = ""
                db.session.commit()
    return h

# ── info fetchers ──────────────────────────────────────────────────────────────
def get_info(url):
    url = clean_url(url)
    with yt_dlp.YoutubeDL(dict(_base(), skip_download=True)) as ydl:
        info = ydl.extract_info(url, download=False)
    sec    = int(info.get("duration") or 0)
    thumbs = info.get("thumbnails") or []
    thumb  = info.get("thumbnail", "")
    if thumbs:
        thumb = max(thumbs, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0)).get("url", thumb)
    return dict(
        title=info.get("title", "Unknown"), thumbnail=thumb,
        duration="{}:{:02d}".format(sec // 60, sec % 60),
        uploader=info.get("uploader") or info.get("channel") or "N/A",
        clean_url=url, video_id=extract_vid(url) or "",
    )

def get_playlist_info(url):
    with yt_dlp.YoutubeDL(dict(_base(), skip_download=True, extract_flat=True, playlistend=100)) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or []
    result = []
    for e in entries:
        vid = e.get("id", "")
        if not (vid or e.get("url")): continue
        sec = int(e.get("duration") or 0)
        result.append(dict(
            title=e.get("title", "Unknown"),
            url="https://www.youtube.com/watch?v=" + vid if vid else e.get("url", ""),
            duration="{}:{:02d}".format(sec // 60, sec % 60) if sec else "N/A",
            thumbnail=e.get("thumbnail", "") or "https://i.ytimg.com/vi/{}/mqdefault.jpg".format(vid),
            video_id=vid,
        ))
    return dict(title=info.get("title", "Playlist"), count=len(result), entries=result)

# ── queue worker ───────────────────────────────────────────────────────────────
def _queue_worker():
    global active_count
    while True:
        time.sleep(0.8)
        with queue_lock:
            if active_count >= MAX_CONCURRENT or not download_queue:
                continue
            item = download_queue.pop(0)
            active_count += 1
        uid, url, fmt, aq = item
        with app.app_context():
            row = Download.query.filter_by(uid=uid).first()
            if row:
                row.status = "downloading"
                db.session.commit()
        threading.Thread(target=_run_dl, args=(uid, url, fmt, aq), daemon=True).start()

threading.Thread(target=_queue_worker, daemon=True).start()

def _run_dl(uid, url, fmt, aq):
    global active_count
    try:
        do_download(uid, url, fmt, aq)
    finally:
        with queue_lock:
            active_count = max(0, active_count - 1)

def do_download(uid, url, fmt, audio_quality="320"):
    with app.app_context():
        row = Download.query.filter_by(uid=uid).first()
        if not row: return
        url = clean_url(url)

        safe    = row.custom_name.strip() if row.custom_name and row.custom_name.strip() else "%(title)s"
        outtmpl = os.path.join(DL_DIR, uid + "_" + safe + ".%(ext)s")
        opts    = dict(_base(), outtmpl=outtmpl, progress_hooks=[_hook(uid)])

        if fmt == "mp3":
            # Fix: format audio lebih fleksibel + fallback tanpa ffmpeg
            opts["format"] = "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best"
            if HAVE_FF:
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": audio_quality,
                }]
            else:
                opts["format"] = "bestaudio/best"

        elif fmt == "mp4":
            if HAVE_FF:
                # Fix: format lebih fleksibel, tidak terlalu ketat ext=mp4
                opts["format"] = (
                    "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                    "/bestvideo[height<=1080]+bestaudio"
                    "/best[height<=1080]/best"
                )
                opts["merge_output_format"] = "mp4"
                opts["postprocessor_args"] = {
                    "ffmpeg": ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
                }
            else:
                opts["format"] = "best[height<=1080][ext=mp4]/best[ext=mp4]/best"

        else:
            # HD Full — kualitas tertinggi tanpa batasan resolusi
            if HAVE_FF:
                opts["format"] = (
                    "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                    "/bestvideo+bestaudio"
                    "/best"
                )
                opts["merge_output_format"] = "mp4"
                opts["postprocessor_args"] = {
                    "ffmpeg": ["-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart"]
                }
            else:
                opts["format"] = "bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best"

        def _cleanup_parts():
            for fname in os.listdir(DL_DIR):
                if fname.startswith(uid) and fname.endswith(".part"):
                    try: os.remove(os.path.join(DL_DIR, fname))
                    except Exception: pass

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(url, download=True)

            if uid in cancelled_jobs:
                cancelled_jobs.discard(uid)
                row.status = "cancelled"; row.error_msg = "Download dibatalkan."
                db.session.commit(); return

            # Fix: abaikan file .part (download tidak selesai), cari file final saja
            found = None
            for fname in sorted(os.listdir(DL_DIR)):
                if fname.startswith(uid) and not fname.endswith(".part"):
                    found = fname; break

            if found:
                fp = os.path.join(DL_DIR, found)
                row.filename = found
                row.filesize = "{:.2f} MB".format(os.path.getsize(fp) / 1048576)
                row.status = "done"; row.progress = 100; row.speed = ""; row.eta = ""
                row.completed_at = datetime.utcnow()
            else:
                _cleanup_parts()
                row.status = "error"; row.error_msg = "File tidak ditemukan setelah download."

        except Exception as exc:
            msg = str(exc)
            _cleanup_parts()
            if "dibatalkan" in msg.lower():
                row.status = "cancelled"; row.error_msg = "Download dibatalkan."; cancelled_jobs.discard(uid)
            else:
                row.status = "error"; row.error_msg = friendly(exc)
        db.session.commit()

# ── routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", ffmpeg_ok=HAVE_FF, disk_free=round(disk_free_gb(), 1))

@app.route("/api/info", methods=["POST"])
def api_info():
    url = (request.get_json() or {}).get("url", "").strip()
    if not url: return jsonify(success=False, error="URL tidak boleh kosong.")
    try:
        if "list=" in url and ("playlist" in url or "watch" not in url):
            return jsonify(success=True, is_playlist=True, info=get_playlist_info(url))
        return jsonify(success=True, is_playlist=False, info=get_info(url))
    except Exception as e:
        return jsonify(success=False, error=friendly(e))

@app.route("/api/search", methods=["POST"])
def api_search():
    q = (request.get_json() or {}).get("q", "").strip()
    if not q: return jsonify(success=False, error="Kata kunci kosong.")
    try:
        with yt_dlp.YoutubeDL(dict(_base(), skip_download=True, extract_flat=True, quiet=True)) as ydl:
            info = ydl.extract_info("ytsearch10:" + q, download=False)
        results = []
        for e in (info.get("entries") or []):
            sec = int(e.get("duration") or 0)
            vid = e.get("id", "")
            results.append(dict(
                title=e.get("title", "Unknown"),
                url="https://www.youtube.com/watch?v=" + vid if vid else "",
                thumbnail=e.get("thumbnail", "") or "https://i.ytimg.com/vi/{}/mqdefault.jpg".format(vid),
                duration="{}:{:02d}".format(sec // 60, sec % 60) if sec else "N/A",
                uploader=e.get("uploader") or e.get("channel") or "N/A",
                views=e.get("view_count", 0), video_id=vid,
            ))
        return jsonify(success=True, results=results)
    except Exception as e:
        return jsonify(success=False, error=friendly(e))

@app.route("/api/trending")
def api_trending():
    queries = ["lagu populer indonesia 2025", "trending music indonesia terbaru", "top hits indonesia viral"]
    for q in queries:
        try:
            with yt_dlp.YoutubeDL(dict(_base(), skip_download=True, extract_flat=True, quiet=True)) as ydl:
                info = ydl.extract_info("ytsearch12:" + q, download=False)
            results = []
            for e in (info.get("entries") or []):
                sec = int(e.get("duration") or 0)
                vid = e.get("id", "")
                if not vid: continue
                results.append(dict(
                    title=e.get("title", "Unknown"),
                    url="https://www.youtube.com/watch?v=" + vid,
                    thumbnail=e.get("thumbnail", "") or "https://i.ytimg.com/vi/{}/mqdefault.jpg".format(vid),
                    duration="{}:{:02d}".format(sec // 60, sec % 60) if sec else "N/A",
                    uploader=e.get("uploader") or e.get("channel") or "N/A",
                    views=e.get("view_count", 0), video_id=vid,
                ))
            if results:
                return jsonify(success=True, results=results)
        except Exception:
            continue
    return jsonify(success=False, error="Gagal memuat trending.")

@app.route("/api/download", methods=["POST"])
def api_download():
    data  = request.get_json() or {}
    url   = data.get("url", "").strip()
    fmt   = data.get("format", "mp4")
    aq    = data.get("audio_quality", "320")
    cname = data.get("custom_name", "").strip()
    if not url: return jsonify(success=False, error="URL tidak valid.")
    if fmt == "mp3" and not HAVE_FF: return jsonify(success=False, error="ffmpeg diperlukan untuk MP3.")
    if disk_free_gb() < 0.5: return jsonify(success=False, error="Disk hampir penuh! Hapus file lama dulu.")
    uid = str(uuid.uuid4())
    row = Download(uid=uid, url=url, title=data.get("title", "Unknown"), custom_name=cname,
                   thumbnail=data.get("thumbnail", ""), duration=data.get("duration", "N/A"),
                   uploader=data.get("uploader", "N/A"), format_type=fmt, audio_quality=aq, status="queued")
    db.session.add(row); db.session.commit()
    with queue_lock:
        download_queue.append((uid, url, fmt, aq))
    return jsonify(success=True, uid=uid, queue_pos=len(download_queue))

@app.route("/api/rename/<uid>", methods=["POST"])
def api_rename(uid):
    new_name = (request.get_json() or {}).get("name", "").strip()
    if not new_name: return jsonify(success=False, error="Nama tidak boleh kosong.")
    row = Download.query.filter_by(uid=uid).first()
    if not row: return jsonify(success=False, error="Tidak ditemukan.")
    row.custom_name = new_name
    if row.status == "done" and row.filename:
        old_fp = os.path.join(DL_DIR, row.filename)
        ext    = row.filename.rsplit(".", 1)[-1] if "." in row.filename else ""
        new_fn = uid + "_" + new_name + ("." + ext if ext else "")
        try:
            if os.path.exists(old_fp):
                os.rename(old_fp, os.path.join(DL_DIR, new_fn))
                row.filename = new_fn
        except Exception as e:
            return jsonify(success=False, error=str(e))
    db.session.commit()
    return jsonify(success=True)

@app.route("/api/cancel/<uid>", methods=["POST"])
def api_cancel(uid):
    cancelled_jobs.add(uid)
    with queue_lock:
        for item in list(download_queue):
            if item[0] == uid:
                download_queue.remove(item)
    row = Download.query.filter_by(uid=uid).first()
    if row and row.status in ("pending", "queued", "downloading", "processing"):
        row.status = "cancelled"; row.error_msg = "Dibatalkan."; db.session.commit()
    return jsonify(success=True)

@app.route("/api/status/<uid>")
def api_status(uid):
    row = Download.query.filter_by(uid=uid).first()
    if not row: return jsonify(success=False, data={})
    data = row.to_dict()
    with queue_lock:
        data["queue_pos"] = next((i + 1 for i, it in enumerate(download_queue) if it[0] == uid), 0)
    return jsonify(success=True, data=data)

@app.route("/api/stream/<uid>")
def api_stream(uid):
    row = Download.query.filter_by(uid=uid).first()
    if not row or row.status != "done": return "File belum siap", 404
    fp = os.path.join(DL_DIR, row.filename)
    if not os.path.exists(fp): return "File tidak ada", 404
    ext      = fp.rsplit(".", 1)[-1].lower() if "." in fp else ""
    mime     = "audio/mpeg" if ext == "mp3" else "video/mp4"
    filesize = os.path.getsize(fp)
    rng      = request.headers.get("Range")
    if rng:
        parts  = rng.replace("bytes=", "").split("-")
        start  = int(parts[0])
        end    = int(parts[1]) if len(parts) > 1 and parts[1] else filesize - 1
        length = end - start + 1
        def _gen():
            with open(fp, "rb") as f:
                f.seek(start)
                rem = length
                while rem > 0:
                    chunk = f.read(min(65536, rem))
                    if not chunk: break
                    rem -= len(chunk)
                    yield chunk
        return Response(_gen(), 206, mimetype=mime,
            headers={"Content-Range": "bytes {}-{}/{}".format(start, end, filesize),
                     "Accept-Ranges": "bytes", "Content-Length": str(length), "Content-Disposition": "inline"})
    return send_file(fp, mimetype=mime, conditional=True)

@app.route("/api/file/<uid>")
def api_file(uid):
    row = Download.query.filter_by(uid=uid).first()
    if not row or row.status != "done": return "File belum siap", 404
    fp = os.path.join(DL_DIR, row.filename)
    if not os.path.exists(fp): return "File tidak ada", 404
    dl_name = row.custom_name.strip() if row.custom_name and row.custom_name.strip() else row.filename
    return send_file(fp, as_attachment=True, download_name=dl_name)

@app.route("/api/open/<uid>", methods=["POST"])
def api_open(uid):
    row = Download.query.filter_by(uid=uid).first()
    if not row or row.status != "done": return jsonify(success=False, error="File belum siap")
    fp = os.path.join(DL_DIR, row.filename)
    if not os.path.exists(fp): return jsonify(success=False, error="File tidak ada")
    try:
        system = platform.system()
        if system == "Windows":
            sp.Popen(["explorer", "/select,", fp])
        elif system == "Darwin":
            sp.Popen(["open", "-R", fp])
        else:
            sp.Popen(["xdg-open", os.path.dirname(fp)])
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))

@app.route("/api/history")
def api_history():
    page  = request.args.get("page", 1, type=int)
    per   = request.args.get("per", 50, type=int)
    q     = Download.query.order_by(Download.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per).limit(per).all()
    return jsonify(items=[r.to_dict() for r in items], total=total, page=page, per=per)

@app.route("/api/delete/<uid>", methods=["DELETE"])
def api_delete(uid):
    row = Download.query.filter_by(uid=uid).first()
    if not row: return jsonify(success=False)
    if row.filename:
        fp = os.path.join(DL_DIR, row.filename)
        if os.path.exists(fp):
            try: os.remove(fp)
            except Exception: pass
    db.session.delete(row); db.session.commit()
    return jsonify(success=True)

@app.route("/api/stats")
def api_stats():
    free = disk_free_gb()
    used = sum(os.path.getsize(os.path.join(DL_DIR, f))
               for f in os.listdir(DL_DIR) if os.path.isfile(os.path.join(DL_DIR, f))) / (1024 ** 3)
    return jsonify(
        total=Download.query.count(), done=Download.query.filter_by(status="done").count(),
        mp3=Download.query.filter_by(format_type="mp3", status="done").count(),
        mp4=Download.query.filter_by(format_type="mp4", status="done").count(),
        hd=Download.query.filter_by(format_type="hd", status="done").count(),
        ffmpeg=HAVE_FF, disk_free=round(free, 1), disk_used=round(used, 2),
        queue_len=len(download_queue), active=active_count,
    )

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  BeatDrop Pro 2026")
    print("  http://localhost:5000")
    print("  ffmpeg:", "OK" if HAVE_FF else "Tidak ada - jalankan install.py")
    print("="*50 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
