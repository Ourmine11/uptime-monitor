# file: app.py
from flask import Flask, request, jsonify, send_file, render_template
import os, threading, time, socket, sqlite3
from datetime import datetime
import requests
from urllib.parse import urlparse
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

VALID_USERNAME = os.getenv("UPTIME_USERNAME", "admin")
VALID_PASSWORD = os.getenv("UPTIME_PASSWORD", "1234")
VALID_TOKEN = os.getenv("UPTIME_TOKEN", "demo-token")
DB_FILE = "uptime_logs.db"

monitoring = {
    "running": False, "url": None,
    "thread": None, "last_status": None, "last_error": None
}
interval = 10

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS uptime_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            url TEXT NOT NULL,
            status INTEGER NOT NULL
        )""")
init_db()

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {VALID_TOKEN}":
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper

def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and parsed.netloc != ""
    except:
        return False

def log_status(ok: bool):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("INSERT INTO uptime_logs (timestamp, url, status) VALUES (?, ?, ?)", (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            monitoring["url"],
            1 if ok else 0
        ))

def monitor():
    while monitoring["running"]:
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
                monitoring["last_error"] = f"HTTP {res.status_code} or non-HTML"
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
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.execute(
            "SELECT timestamp, status FROM uptime_logs WHERE url = ? ORDER BY id DESC LIMIT 50",
            (monitoring["url"],)
        )
        for ts, val in reversed(cur.fetchall()):
            results.append({"x": ts, "y": val})
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
