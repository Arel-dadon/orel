from flask import (
    Flask, render_template, request, redirect, url_for, send_file,
    make_response, send_from_directory
)
from pathlib import Path
import sqlite3, io, qrcode, socket, subprocess, re, os, uuid
from werkzeug.utils import secure_filename
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

APP_DIR = Path(__file__).parent
# ✅ Use /tmp for writable storage on Vercel
WRITE_DIR = Path('/tmp')
DB_PATH = WRITE_DIR / 'guestbook.db'
UPLOAD_DIR = WRITE_DIR / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTS = {"jpg", "jpeg", "png", "gif"}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# -------------------- helpers --------------------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                caption TEXT,
                filename TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def get_server_ip():
    try:
        out = subprocess.check_output(["hostname", "-I"]).decode().strip()
        if out: return out.split()[0]
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "Unknown"

def get_client_ip(req):
    xff = req.headers.get("X-Forwarded-For", "")
    if xff: return xff.split(",")[0].strip()
    return req.remote_addr or ""

def try_reverse_dns(ip: str):
    if not ip: return None
    try:
        host, _, _ = socket.gethostbyaddr(ip)
        return host.split(".")[0]
    except Exception:
        try:
            fqdn = socket.getfqdn(ip)
            if fqdn and fqdn != ip: return fqdn.split(".")[0]
        except Exception:
            pass
    return None

UA_BROWSER_PATTERNS = [
    (r"Edg/[\d.]+", "Edge"),
    (r"Chrome/[\d.]+", "Chrome"),
    (r"CriOS/[\d.]+", "Chrome iOS"),
    (r"Firefox/[\d.]+", "Firefox"),
    (r"Safari/[\d.]+", "Safari"),
]
UA_OS_PATTERNS = [
    (r"Windows NT 11|Windows 11", "Windows 11"),
    (r"Windows NT 10", "Windows 10"),
    (r"Windows NT", "Windows"),
    (r"Android", "Android"),
    (r"iPhone|iPad|iOS", "iOS"),
    (r"Mac OS X|Macintosh", "macOS"),
    (r"Linux", "Linux"),
]

def summarize_user_agent(ua: str) -> str:
    if not ua: return "Unknown device"
    browser, osname = "Browser", "Device"
    for pat, name in UA_BROWSER_PATTERNS:
        if re.search(pat, ua): browser = name; break
    for pat, name in UA_OS_PATTERNS:
        if re.search(pat, ua): osname = name; break
    return f"{browser} on {osname}"

def detect_device_name(req):
    ip = get_client_ip(req)
    ua = req.headers.get("User-Agent", "")
    ua_summary = summarize_user_agent(ua)
    hostname = try_reverse_dns(ip)
    device_label = hostname or ua_summary
    return device_label, ip, ua_summary

def load_font(size: int):
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]:
        if Path(p).exists():
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()

# -------------------- routes --------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = (request.form.get("guest_name") or "").strip()[:60]
        resp = make_response(redirect(url_for("index")))
        if name:
            resp.set_cookie("guest_name", name, max_age=60*60*24*365)
        return resp

    device_label, ip, ua_summary = detect_device_name(request)
    server_ip = get_server_ip()
    cookie_name = request.cookies.get("guest_name")
    return render_template("index.html",
                           device_label=device_label,
                           client_ip=ip,
                           ua_summary=ua_summary,
                           server_ip=server_ip,
                           cookie_name=cookie_name)

@app.route("/guestbook", methods=["GET", "POST"])
def guestbook():
    if request.method == "POST":
        name = (request.form.get("name") or request.cookies.get("guest_name") or "").strip()[:60]
        message = (request.form.get("message") or "").strip()[:500]
        if name and message:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("INSERT INTO entries (name, message) VALUES (?, ?)", (name, message))
                conn.commit()
        return redirect(url_for("guestbook"))

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT name, message, created_at FROM entries ORDER BY id DESC LIMIT 100")
        entries = c.fetchall()
    return render_template("guestbook.html", entries=entries)

@app.route("/memory-wall", methods=["GET", "POST"])
def memory_wall():
    if request.method == "POST":
        name = (request.form.get("name") or request.cookies.get("guest_name") or "").strip()[:60]
        caption = (request.form.get("caption") or "").strip()[:140]
        file = request.files.get("photo")
        if name and file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext in ALLOWED_EXTS:
                safe = secure_filename(file.filename)
                unique = f"{uuid.uuid4().hex}.{ext}"
                path = UPLOAD_DIR / unique
                file.save(path)
                with sqlite3.connect(DB_PATH) as conn:
                    c = conn.cursor()
                    c.execute("INSERT INTO photos (name, caption, filename) VALUES (?, ?, ?)",
                              (name, caption, unique))
                    conn.commit()
        return redirect(url_for("memory_wall"))

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT name, caption, filename, created_at FROM photos ORDER BY id DESC LIMIT 60")
        photos = c.fetchall()
    return render_template("memory_wall.html", photos=photos)

@app.route("/u/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, conditional=True)

@app.route("/wifi")
def wifi():
    ssid = "Dahan"
    password = "100200300"
    auth_type = "WPA"
    return render_template("wifi.html", ssid=ssid, password=password, auth_type=auth_type)

@app.route("/wifi/qr.png")
def wifi_qr_png():
    ssid = "Dahan"
    password = "100200300"
    auth_type = "WPA"
    payload = f"WIFI:T:{auth_type};S:{ssid};P:{password};H:false;;"
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

# ------- Cool feature: Personal Guest Pass -------
@app.route("/guest-pass", methods=["GET"])
def guest_pass_form():
    default_name = request.cookies.get("guest_name", "")
    return render_template("guest_pass.html", default_name=default_name)

@app.route("/guest-pass.png", methods=["POST"])
def guest_pass_png():
    name = (request.form.get("name") or "Guest").strip()[:40]
    ssid = "Dahan"
    password = "100200300"
    auth_type = "WPA"
    today = datetime.now().strftime("%Y-%m-%d")

    payload = f"WIFI:T:{auth_type};S:{ssid};P:{password};H:false;;"
    qr_img = qrcode.make(payload).resize((420, 420))

    W, H = 1200, 630
    bg = Image.new("RGB", (W, H), (11, 18, 32))  # dark navy
    draw = ImageDraw.Draw(bg)

    pad = 40
    card_r = (18, 27, 46)
    border = (32, 47, 78)
    draw.rectangle([pad, pad, W-pad, H-pad], fill=card_r, outline=border, width=3)

    title_f = load_font(56)
    name_f  = load_font(72)
    text_f  = load_font(36)
    small_f = load_font(28)

    draw.text((pad+40, pad+30), "Guest Pass", font=title_f, fill=(230, 238, 245))
    draw.text((pad+40, pad+120), name, font=name_f, fill=(230, 238, 245))

    y = pad+220
    draw.text((pad+40, y), f"Date: {today}", font=text_f, fill=(170, 179, 197)); y += 50
    draw.text((pad+40, y), f"Wi-Fi: {ssid}", font=text_f, fill=(170, 179, 197)); y += 50
    draw.text((pad+40, y), f"Password: {password}", font=text_f, fill=(170, 179, 197)); y += 50
    draw.text((pad+40, y), f"Auth: {auth_type}", font=text_f, fill=(170, 179, 197))

    qr_x = W - pad - 460
    qr_y = pad + 110
    draw.rectangle([qr_x-10, qr_y-10, qr_x+420+10, qr_y+420+10], outline=border, width=3)
    bg.paste(qr_img, (qr_x, qr_y))

    draw.text((pad+40, H - pad - 40),
              "Scan to join Wi-Fi instantly • Hosted on our Raspberry Pi",
              font=small_f, fill=(170, 179, 197))

    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    buf.seek(0)
    filename = f"guest-pass-{name.lower().replace(' ','-')}.png"
    return send_file(buf, mimetype="image/png",
                     as_attachment=True, download_name=filename)

# -------------------------------------------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001)
else:
    init_db()

# -------- Web Photo Booth (camera in browser) --------
from flask import jsonify
import base64

@app.route("/photobooth", methods=["GET"])
def photobooth():
    default_name = request.cookies.get("guest_name", "")
    return render_template("photobooth.html", default_name=default_name)

@app.route("/photobooth/upload", methods=["POST"])
def photobooth_upload():
    """
    Expects JSON:
      { "image": "data:image/png;base64,....", "name": "...", "caption": "..." }
    Saves PNG into uploads and inserts into photos table.
    """
    data = request.get_json(force=True, silent=True) or {}
    data_url = (data.get("image") or "")[:10_000_000]  # guard
    name = (data.get("name") or request.cookies.get("guest_name") or "Guest").strip()[:60]
    caption = (data.get("caption") or "").strip()[:140]

    if not data_url.startswith("data:image/png;base64,"):
        return jsonify({"ok": False, "error": "Invalid image data"}), 400

    b64 = data_url.split(",", 1)[1]
    raw = base64.b64decode(b64)

    filename = f"{uuid.uuid4().hex}.png"
    (UPLOAD_DIR / filename).write_bytes(raw)

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO photos (name, caption, filename) VALUES (?, ?, ?)",
                  (name, caption, filename))
        conn.commit()

    return jsonify({"ok": True, "filename": filename, "url": url_for("uploaded_file", filename=filename)})

# ---------- Party TV Mode ----------
from flask import jsonify

@app.route("/api/photos")
def api_photos():
    """Return latest photo metadata for slideshow."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT filename, name, caption, created_at FROM photos ORDER BY id DESC LIMIT 200")
        rows = c.fetchall()
    items = [
        dict(
            url=url_for("uploaded_file", filename=r["filename"]),
            name=r["name"], caption=r["caption"], created_at=r["created_at"]
        ) for r in rows
    ]
    return jsonify(items)

@app.route("/tv")
def tv_mode():
    """Fullscreen slideshow with live updates + QR to Photo Booth."""
    # absolute URL for photobooth QR
    base = request.host_url.rstrip("/")
    booth_url = f"{base}{url_for('photobooth')}"
    return render_template("tv.html", booth_url=booth_url)

@app.route("/tv/qr.png")
def tv_qr():
    """QR pointing to the Photo Booth page."""
    base = request.host_url.rstrip("/")
    booth_url = f"{base}{url_for('photobooth')}"
    img = qrcode.make(booth_url)
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route("/wow")
def wow():
    # use remembered name, otherwise device label
    cookie_name = request.cookies.get("guest_name")
    if cookie_name:
        display_name = cookie_name
    else:
        device_label, *_ = detect_device_name(request)
        display_name = device_label
    return render_template("wow.html", display_name=display_name)
# ---------- Romantic bundle: Star Map + Secret + Romantic WOW ----------

from datetime import datetime
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import math

# (A) SECRET PAGE
@app.route("/secret")
def secret():
    # Customize your message and optional name here (or pass ?name=… in URL)
    name = request.args.get("name") or request.cookies.get("guest_name") or detect_device_name(request)[0]
    msg  = request.args.get("msg") or "You’re my favorite human in the whole universe. 💫"
    return render_template("secret.html", name=name, msg=msg)

# (B) ROMANTIC WOW PAGE (soft music + hearts)
@app.route("/wow")
def romantic_wow():
    name = request.args.get("name") or request.cookies.get("guest_name") or detect_device_name(request)[0]
    return render_template("wow_romantic.html", display_name=name)

# (C) STAR MAP PAGE — HTML wrapper
@app.route("/starmap")
def starmap_page():
    # Defaults (change these to your story)
    # Example: the night you met: 2023-07-14 21:30 at Tel Aviv
    return render_template("starmap.html",
                           default_date="2023-07-14",
                           default_time="21:30",
                           default_lat="32.0853",
                           default_lon="34.7818",
                           default_title="The sky when we met ✨",
                           default_caption="Under this sky, everything began.")

# (D) STAR MAP IMAGE GENERATOR (returns PNG)
@app.route("/starmap.png")
def starmap_png():
    # Query params: date=YYYY-MM-DD, time=HH:MM (24h), lat, lon, title, caption
    date_s  = request.args.get("date") or "2023-07-14"
    time_s  = request.args.get("time") or "21:30"
    lat     = float(request.args.get("lat") or 32.0853)
    lon     = float(request.args.get("lon") or 34.7818)
    title   = (request.args.get("title") or "The sky we shared").strip()[:80]
    caption = (request.args.get("caption") or "").strip()[:160]

    # Parse datetime (local assumed)
    dt = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M")

    # Build star positions with Skyfield (bright-star subset to keep it fast)
    try:
        from skyfield.api import load, Star, wgs84
        ts = load.timescale()
        t = ts.from_datetime(dt)
        eph = load('de421.bsp')  # auto-download once
        earth = eph['earth']
        obs = wgs84.latlon(latitude_degrees=lat, longitude_degrees=lon)

        # Bright stars RA/Dec (deg) and names (hand-picked 18 brightest)
        BRIGHT = [
            ("Sirius",     101.2875, -16.7161),
            ("Canopus",    95.9879,  -52.6957),
            ("Arcturus",   213.9153,  19.1825),
            ("Vega",       279.2347,  38.7837),
            ("Capella",    79.1723,   45.9979),
            ("Rigel",      78.6345,   -8.2016),
            ("Procyon",    114.8255,   5.2249),
            ("Betelgeuse", 88.7929,    7.4071),
            ("Achernar",   24.4286,  -57.2367),
            ("Altair",     297.6958,   8.8683),
            ("Aldebaran",  68.9802,   16.5093),
            ("Antares",    247.3519, -26.4320),
            ("Spica",      201.2983, -11.1613),
            ("Pollux",     116.3289,  28.0262),
            ("Fomalhaut",  344.4128, -29.6222),
            ("Deneb",      310.3579,  45.2803),
            ("Regulus",    152.0929,  11.9672),
            ("Hadar",      210.9558, -60.3730),
        ]

        stars_altaz = []
        for name, ra_deg, dec_deg in BRIGHT:
            s = Star(ra_hours=ra_deg/15.0, dec_degrees=dec_deg)
            app = (earth + obs).at(t).observe(s).apparent()
            alt, az, _ = app.altaz()
            alt_deg = alt.degrees
            az_deg  = az.degrees
            if alt_deg > 0:  # only visible stars
                stars_altaz.append((name, alt_deg, az_deg))

    except Exception as e:
        # If skyfield fails, fall back to empty sky (shouldn’t happen after first run)
        stars_altaz = []

    # Render polar star chart to PNG
    W, H = 1200, 1600
    img = Image.new("RGB", (W, H), (6, 10, 20))
    draw = ImageDraw.Draw(img)

    # Title & caption fonts
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
        cap_font   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except:
        title_font = cap_font = small_font = ImageFont.load_default()

    # Title
    draw.text((W//2, 80), title, fill=(230,240,255), anchor="mm", font=title_font)

    # Circle bounds
    R = 650
    CX, CY = W//2, H//2 + 80
    draw.ellipse((CX-R, CY-R, CX+R, CY+R), outline=(26,40,80), width=3)

    # Altitude circles every 15°
    for alt in [15,30,45,60,75]:
        r = R * (1 - alt/90.0)
        draw.ellipse((CX-r, CY-r, CX+r, CY+r), outline=(20,30,60))

    # Cardinal directions
    for label, ang in [("N",0),("E",90),("S",180),("W",270)]:
        x = CX + (R+28)*math.sin(math.radians(ang))
        y = CY - (R+28)*math.cos(math.radians(ang))
        draw.text((x,y), label, fill=(160,180,220), anchor="mm", font=cap_font)

    # Stars
    for name, alt_deg, az_deg in stars_altaz:
        r = R * (1 - alt_deg/90.0)
        theta = math.radians(az_deg)
        x = CX + r * math.sin(theta)
        y = CY - r * math.cos(theta)
        # star dot
        draw.ellipse((x-4, y-4, x+4, y+4), fill=(200,220,255))
        # label
        draw.text((x+10, y-2), name, fill=(150,170,220), anchor="ls", font=small_font)

    # Footer (date/time/location)
    footer = f"{date_s} {time_s}  •  lat {lat:.4f}, lon {lon:.4f}"
    draw.text((W//2, H-80), footer, fill=(150,170,210), anchor="mm", font=cap_font)
    if caption:
        draw.text((W//2, 140), caption, fill=(190,200,230), anchor="mm", font=cap_font)

    # Send PNG
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

# --------------------------------------------------------------------