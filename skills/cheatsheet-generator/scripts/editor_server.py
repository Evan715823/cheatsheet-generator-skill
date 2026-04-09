"""Phase 3: Preview & iterative editing server.

Uses a blocking HTTP protocol for communication between browser and Claude:
- Browser POST /request -> server blocks until Claude posts result
- Claude GET /wait_for_request -> server blocks until browser submits request
- Claude POST /result -> unblocks browser, returns updated tex
- POST /quit -> signals shutdown
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser

from flask import Flask, request, jsonify, send_file, send_from_directory
from queue import Queue, Empty
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB upload limit

# --- Shared state ---
TEX_FILE = ""
TEMPLATE_DIR = ""
UPLOAD_DIR = ""
HAS_LATEX = False

# Thread-safe communication between browser and Claude
request_queue = Queue()    # browser -> Claude: modification requests
result_lock = threading.Lock()
result_events = {}         # request_id -> threading.Event
result_store = {}          # request_id -> response data
current_request_id = None  # tracks which request Claude is processing
quit_flag = threading.Event()     # set when user clicks Done


def find_free_port():
    """Let OS assign a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check_latex_tools():
    """Check if latexmk and pdftoppm are available for PDF preview."""
    has_latexmk = shutil.which("latexmk") is not None
    has_pdftoppm = shutil.which("pdftoppm") is not None
    return has_latexmk and has_pdftoppm


def compile_preview():
    """Try to compile tex to PDF and convert first page to PNG."""
    if not HAS_LATEX:
        return
    try:
        workdir = os.path.dirname(TEX_FILE)
        subprocess.run(
            ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
             "-outdir=" + workdir, TEX_FILE],
            capture_output=True, timeout=30
        )
        pdf_path = os.path.splitext(TEX_FILE)[0] + ".pdf"
        if os.path.exists(pdf_path):
            png_base = os.path.join(workdir, ".preview")
            subprocess.run(
                ["pdftoppm", "-png", "-f", "1", "-l", "1", "-r", "150",
                 pdf_path, png_base],
                capture_output=True, timeout=10
            )
    except Exception:
        pass


@app.route("/")
def index():
    """Serve the editor UI."""
    template_path = os.path.join(TEMPLATE_DIR, "editor_ui.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


@app.route("/tex")
def get_tex():
    """Return current tex source."""
    try:
        with open(TEX_FILE, "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/plain; charset=utf-8"}
    except FileNotFoundError:
        return "% File not found", 404


@app.route("/preview.png")
def get_preview():
    """Serve PDF preview PNG if available."""
    workdir = os.path.dirname(TEX_FILE)
    # pdftoppm outputs .preview-1.png
    png_path = os.path.join(workdir, ".preview-1.png")
    if os.path.exists(png_path):
        return send_file(png_path, mimetype="image/png")
    return "", 404


@app.route("/upload_image", methods=["POST"])
def upload_image():
    """Handle image upload from browser. Save to upload dir and return path."""
    if "image" not in request.files:
        return jsonify({"error": "No image"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No filename"}), 400

    filename = secure_filename(file.filename)
    # secure_filename returns empty for pure Unicode names (e.g. Chinese)
    if not filename:
        ext = os.path.splitext(file.filename)[1] if file.filename else ""
        # Sanitize extension
        ext = re.sub(r'[^\w.]', '', ext)
        filename = f"upload_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    file.save(filepath)
    return jsonify({"path": filepath, "name": filename})


@app.route("/uploaded/<filename>")
def serve_uploaded(filename):
    """Serve uploaded images for thumbnail preview."""
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/request", methods=["POST"])
def handle_request():
    """Browser submits a modification request. Blocks until Claude processes it."""
    data = request.get_json()
    edit_text = data.get("request", "")
    images = data.get("images", [])

    if not edit_text.strip():
        return jsonify({"error": "Empty request"}), 400

    # Create per-request event and ID
    req_id = uuid.uuid4().hex[:8]
    event = threading.Event()
    with result_lock:
        result_events[req_id] = event
        result_store[req_id] = {}

    # Put request in queue for Claude to pick up (with images)
    request_queue.put({"text": edit_text, "images": images, "id": req_id})

    # Block until Claude posts result (no timeout — frontend shows progress)
    event.wait()

    # Return result to browser and clean up
    with result_lock:
        data = result_store.pop(req_id, {})
        result_events.pop(req_id, None)
    return jsonify(data)


@app.route("/wait_for_request")
def wait_for_request():
    """Claude calls this and blocks until a request arrives or quit is signaled."""
    while True:
        # Check quit first
        if quit_flag.is_set():
            return jsonify({"type": "quit"})

        try:
            item = request_queue.get(timeout=1.0)
            global current_request_id
            if isinstance(item, dict):
                current_request_id = item.get("id")
                return jsonify({"type": "request", "text": item["text"], "images": item.get("images", [])})
            else:
                current_request_id = None
                return jsonify({"type": "request", "text": item})
        except Empty:
            # Keep waiting — check quit flag again
            continue


@app.route("/result", methods=["POST"])
def post_result():
    """Claude posts the result of processing a modification request."""
    data = request.get_json()
    summary = data.get("summary", "")
    tex_content = data.get("tex", "")

    # Write updated tex to file
    if tex_content:
        with open(TEX_FILE, "w", encoding="utf-8") as f:
            f.write(tex_content)

        # Try to compile preview in background
        if HAS_LATEX:
            threading.Thread(target=compile_preview, daemon=True).start()

    # Store result and unblock the waiting browser request
    with result_lock:
        if current_request_id and current_request_id in result_store:
            result_store[current_request_id] = {
                "tex": tex_content,
                "summary": summary
            }
        if current_request_id and current_request_id in result_events:
            result_events[current_request_id].set()

    return jsonify({"status": "ok"})


@app.route("/quit", methods=["POST"])
def handle_quit():
    """User clicks Done. Signal quit and schedule shutdown."""
    quit_flag.set()

    # Unblock any pending /request calls
    with result_lock:
        for req_id, event in result_events.items():
            result_store[req_id] = {"tex": "", "summary": "Session ended"}
            event.set()

    # Schedule server exit
    threading.Timer(1.0, lambda: os._exit(0)).start()
    return jsonify({"status": "quitting"})


def main():
    parser = argparse.ArgumentParser(description="Cheatsheet editor server")
    parser.add_argument("--texfile", required=True, help="Path to cheatsheet.tex")
    args = parser.parse_args()

    global TEX_FILE, TEMPLATE_DIR, UPLOAD_DIR, HAS_LATEX
    TEX_FILE = os.path.abspath(args.texfile)
    TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")
    UPLOAD_DIR = os.path.join(os.path.dirname(TEX_FILE), ".uploads")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    HAS_LATEX = check_latex_tools()

    if HAS_LATEX:
        print("PDF preview enabled (latexmk + pdftoppm found)", flush=True)
        compile_preview()
    else:
        print("PDF preview disabled (latexmk/pdftoppm not found)", flush=True)

    port = find_free_port()
    url = f"http://127.0.0.1:{port}"

    # Print port for Claude to capture
    print(f"EDITOR_SERVER_PORT={port}", flush=True)
    print(f"Opening {url}", flush=True)

    # Delay browser open so the server is listening before the request arrives.
    # Fixes blank page on macOS where the browser connects faster than Windows.
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
