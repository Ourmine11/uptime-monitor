# file: app.py
from flask import Flask, request, jsonify, send_file, render_template
import os, csv, threading, time, socket
from datetime import datetime
import requests
from urllib.parse import urlparse
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
LOG_FILE = "uptime_logs/uptime_report.csv"
VALID_USERNAME = os.getenv("UPTIME_USERNAME", "admin")
VALID_PASSWORD = os.getenv("UPTIME_PASSWORD", "1234")
VALID_TOKEN = os.getenv("UPTIME_TOKEN", "demo-token")

monitoring = {"running": False, "url": None, "thread": None, "last_status": None, "last_error": None}
interval = 10
os.makedirs("uptime_logs", exist_ok=True)

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {VALID_TOKEN}":
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper

def log_status(ok: bool):
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            monitoring["url"],
            "1" if ok else "0"
        ])

def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and parsed.netloc != ""
    except:
        return False

def monitor():
    while True:
        if not monitoring["running"]:
            break
        try:
            url = monitoring["url"]
            if not is_valid_url(url):
                raise ValueError("Invalid URL format")

            host = urlparse(url).netloc
            socket.gethostbyname(host)

            res = requests.get(url, timeout=5)
            content_type = res.headers.get("Content-Type", "").lower()
            if res.status_code == 200 and "text/html" in content_type and "<html" in res.text.lower():
                monitoring["last_status"] = 1
                monitoring["last_error"] = None
                log_status(True)
            else:
                monitoring["last_status"] = 0
                monitoring["last_error"] = f"Status {res.status_code} or non-HTML"
                log_status(False)
        except Exception as e:
            monitoring["last_status"] = 0
            monitoring["last_error"] = str(e)
            log_status(False)
        time.sleep(interval)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    if data.get("username") == VALID_USERNAME and data.get("password") == VALID_PASSWORD:
        return jsonify({"token": VALID_TOKEN})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/logout", methods=["POST"])
def logout():
    return jsonify({"message": "Logged out"})

@app.route("/start", methods=["POST"])
@require_auth
def start():
    data = request.get_json()
    url = data.get("url", "")
    if not url.startswith("http"):
        url = "http://" + url
    if monitoring["running"]:
        monitoring["running"] = False
        time.sleep(interval + 1)
    monitoring["url"] = url
    monitoring["running"] = True
    monitoring["last_status"] = None
    monitoring["last_error"] = None
    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "URL", "Status"])
    monitoring["thread"] = threading.Thread(target=monitor, daemon=True)
    monitoring["thread"].start()
    return jsonify({"status": "started"})

@app.route("/stop", methods=["POST"])
@require_auth
def stop():
    monitoring["running"] = False
    monitoring["last_status"] = None
    monitoring["last_error"] = None
    return jsonify({"status": "stopped"})

@app.route("/status")
@require_auth
def status():
    return jsonify({
        "running": monitoring["running"],
        "last_status": monitoring["last_status"],
        "last_error": monitoring["last_error"]
    })

@app.route("/logs")
@require_auth
def logs():
    results = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE) as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) == 3:
                    ts, _, val = row
                    val = val.strip()
                    if val in ["0", "1"]:
                        results.append({"x": ts, "y": int(val)})
    return jsonify(results[-50:])

@app.route("/download")
@require_auth
def download():
    return send_file(LOG_FILE, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
