"""Phase 1: Configuration collection server.

Serves a browser form for cheatsheet configuration.
On submit, writes .cheatsheet_config.json and exits.
"""

import argparse
import json
import os
import socket
import sys
import threading
import webbrowser

from flask import Flask, request, jsonify

app = Flask(__name__)

WORKDIR = ""
TEMPLATE_DIR = ""


def find_free_port():
    """Let OS assign a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def scan_files(workdir):
    """Scan workdir for supported material files."""
    extensions = {".pptx", ".pdf", ".md", ".txt", ".png", ".jpg", ".jpeg", ".tex"}
    files = []
    for entry in sorted(os.listdir(workdir)):
        ext = os.path.splitext(entry)[1].lower()
        if ext in extensions:
            files.append({"name": entry, "ext": ext.lstrip(".")})
    return files


def get_ext_class(ext):
    """Map file extension to CSS class."""
    mapping = {
        "pptx": "ext-pptx",
        "pdf": "ext-pdf",
        "md": "ext-md",
        "txt": "ext-txt",
        "tex": "ext-txt",
        "png": "ext-img",
        "jpg": "ext-img",
        "jpeg": "ext-img",
    }
    return mapping.get(ext, "ext-txt")


def build_file_list_html(files):
    """Build HTML for the file checkbox list."""
    if not files:
        return '<div style="color:#8b8fa3;padding:12px;">No supported files found in directory.</div>'
    lines = []
    for f in files:
        css = get_ext_class(f["ext"])
        lines.append(
            f'<div class="file-item">'
            f'<input type="checkbox" checked data-filename="{f["name"]}">'
            f'<span>{f["name"]}</span>'
            f'<span class="file-ext {css}">{f["ext"].upper()}</span>'
            f"</div>"
        )
    return "\n".join(lines)


@app.route("/")
def index():
    """Serve the configuration form."""
    template_path = os.path.join(TEMPLATE_DIR, "config_form.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    files = scan_files(WORKDIR)
    file_html = build_file_list_html(files)
    html = html.replace("%%FILE_LIST%%", file_html)
    return html


@app.route("/submit", methods=["POST"])
def submit():
    """Save config and schedule shutdown."""
    config = request.get_json()
    config_path = os.path.join(WORKDIR, ".cheatsheet_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    # Schedule exit after response is sent
    threading.Timer(1.0, lambda: os._exit(0)).start()
    return jsonify({"status": "ok"})


def main():
    parser = argparse.ArgumentParser(description="Cheatsheet config server")
    parser.add_argument("--workdir", required=True, help="Working directory with materials")
    args = parser.parse_args()

    global WORKDIR, TEMPLATE_DIR
    WORKDIR = os.path.abspath(args.workdir)
    TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")

    port = find_free_port()
    url = f"http://127.0.0.1:{port}"

    # Print port for Claude to capture
    print(f"CONFIG_SERVER_PORT={port}", flush=True)
    print(f"Opening {url}", flush=True)

    webbrowser.open(url)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
