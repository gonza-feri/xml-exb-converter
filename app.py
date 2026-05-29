from flask import Flask, jsonify, render_template, request, send_file, session
import xml.etree.ElementTree as ET
from io import BytesIO
import os
import threading
import uuid
import xmlrpc.client
from nltk.tokenize import wordpunct_tokenize as tokenize
import re
import json

app = Flask(__name__)
app.secret_key = "key"

# ── RUNTIME CONFIG ───────────────────────────────────────────────────────────
RUNTIME_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config_runtime.json")

def load_runtime_config():
    with open(RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_runtime_config(data):
    with open(RUNTIME_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# ── IN-MEMORY JOB STORE ──────────────────────────────────────────────────────
# {job_id: {status, progress, total, content, filename, error}}
jobs      = {}
jobs_lock = threading.Lock()

# ── SETTINGS ROUTES ──────────────────────────────────────────────────────────
@app.route("/get_settings", methods=["GET"])
def get_settings():
    return jsonify(load_runtime_config())

@app.route("/update_settings", methods=["POST"])
def update_settings():
    data   = request.get_json()
    action = data.get("action")
    url    = (data.get("url") or "").strip()

    if not action:
        return jsonify({"status": "error", "message": "Missing action"}), 400

    cfg        = load_runtime_config()
    saved_urls = cfg.get("saved_urls", [])

    if action == "set_active":
        if url not in saved_urls:
            return jsonify({"status": "error", "message": "URL not in saved list"}), 400
        cfg["RPC_SERVER_URL"] = url

    elif action == "add":
        if not url:
            return jsonify({"status": "error", "message": "Empty URL"}), 400
        if url not in saved_urls:
            saved_urls.append(url)
            cfg["saved_urls"] = saved_urls
        cfg["RPC_SERVER_URL"] = url

    elif action == "delete":
        saved_urls = [u for u in saved_urls if u != url]
        cfg["saved_urls"] = saved_urls
        if cfg.get("RPC_SERVER_URL") == url:
            cfg["RPC_SERVER_URL"] = saved_urls[0] if saved_urls else ""

    else:
        return jsonify({"status": "error", "message": "Unknown action"}), 400

    save_runtime_config(cfg)
    return jsonify({"status": "ok", "config": cfg})

# ── UTILITIES ────────────────────────────────────────────────────────────────
def detokenize(text):
    for punct in ['.', '!', '?', ',']:
        text = text.replace(" " + punct, punct)
    for punct in ['-', '/', "'"]:
        text = text.replace(" " + punct + " ", punct)
    return text

def build_proxy():
    cfg = load_runtime_config()
    url = cfg.get("RPC_SERVER_URL", "")
    try:
        proxy = xmlrpc.client.ServerProxy(url, allow_none=True, use_datetime=False)
        return proxy, None
    except Exception as e:
        return None, f"[ERROR] Cannot connect to RPC server: {str(e)}"

def convertText(text, model, proxy):
    lines   = text.split('\n')
    results = ""

    if model == "model1":
        for line in lines:
            line_tok = ' '.join(tokenize(line))
            params   = {"text": line_tok, "align": "false",
                        "report-all-factors": "false", "model": model}
            result   = proxy.translate(params)['text']
            results += detokenize(result) + "\n"
        return results.rstrip("\n"), None

    elif model == "model2":
        for line in lines:
            line_tok = ' '.join(tokenize(line))
            params   = {"text": line_tok, "align": "false",
                        "report-all-factors": "false"}
            result   = proxy.translate(params)['text']
            results += detokenize(result) + "\n"
        return results.rstrip("\n"), None

    return None, "[ERROR] Unknown model selected"

# ── BACKGROUND CONVERSION THREAD ─────────────────────────────────────────────
def process_conversion_thread(job_id, file_bytes, model, original_filename):
    """Parse, convert each event, update progress in the jobs dict."""
    try:
        file_text = file_bytes.decode("utf-8")

        try:
            root = ET.fromstring(file_bytes)
        except ET.ParseError as e:
            with jobs_lock:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"]  = f"Parsing error: {str(e)}"
            return

        # Collect only the verbatim tiers we will process
        target_tiers = [
            t for t in root.iter("tier")
            if t.attrib.get("category") == "v" and t.attrib.get("type") == "t"
        ]
        total_events = sum(len(t.findall("event")) for t in target_tiers)

        with jobs_lock:
            jobs[job_id]["total"] = total_events

        # Build proxy once for the whole conversion
        proxy, proxy_error = build_proxy()
        if proxy_error:
            with jobs_lock:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"]  = proxy_error
            return

        final_text  = file_text
        done_events = 0

        for tier in target_tiers:
            tier_id = tier.attrib.get("id")
            if not tier_id:
                continue

            new_tier = ET.Element("tier", tier.attrib.copy())
            new_tier.set("category", "norm")
            new_tier.set("type",     "t")
            new_tier.set("id",       tier_id + "_norm")

            for event in tier.findall("event"):
                new_event     = ET.Element("event", event.attrib)
                original_text = event.text or ""

                converted, error = convertText(original_text, model, proxy)
                if error:
                    with jobs_lock:
                        jobs[job_id]["status"] = "error"
                        jobs[job_id]["error"]  = error
                    return

                new_event.text = converted
                new_event.tail = "\n"
                new_tier.append(new_event)

                done_events += 1
                with jobs_lock:
                    jobs[job_id]["progress"] = done_events  # real progress ✓

            tier_norm_text = ET.tostring(new_tier, encoding="unicode") + "\n"
            pattern = rf'<tier[^>]*\bid="{re.escape(tier_id)}"[^>]*>'
            match   = re.search(pattern, final_text)

            if match:
                pos        = match.start()
                final_text = final_text[:pos] + tier_norm_text + final_text[pos:]
                tier_tag   = match.group(0)
                modified   = re.sub(r'category="v"', 'category="colloq"', tier_tag)
                modified   = re.sub(r'type="t"',     'type="a"',           modified)
                final_text = final_text.replace(tier_tag, modified)

        # Store completed result
        name, ext = os.path.splitext(original_filename)
        with jobs_lock:
            jobs[job_id]["status"]   = "done"
            jobs[job_id]["content"]  = final_text.encode("utf-8")
            jobs[job_id]["filename"] = f"{name}_converted{ext}"

    except Exception as e:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"]  = f"Unexpected error: {str(e)}"

# ── MAIN ROUTE ───────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html",
                               selected_model=session.get("selected_model"))

    # POST: validate, then start background job
    uploaded_file = request.files.get("file")
    model         = request.form.get("model")
    session["selected_model"] = model

    if not model:
        return render_template("index.html",
                               error="Please select a model before converting.",
                               selected_model=model)
    if not uploaded_file or uploaded_file.filename == "":
        return render_template("index.html",
                               error="No files have been sent.",
                               selected_model=model)

    file_bytes = uploaded_file.read()

    # Quick XML validation before launching the thread
    try:
        ET.fromstring(file_bytes)
    except ET.ParseError as e:
        return render_template("index.html",
                               error=f"Parsing error: not well-formed XML/EXB ({str(e)})",
                               selected_model=model)

    # Create job entry and launch thread
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "status":   "processing",
            "progress": 0,
            "total":    0,
            "content":  None,
            "filename": None,
            "error":    None,
        }

    threading.Thread(
        target=process_conversion_thread,
        args=(job_id, file_bytes, model, uploaded_file.filename),
        daemon=True,
    ).start()

    # Return job_id — client will poll /progress and then /download
    return jsonify({"job_id": job_id})

# ── PROGRESS POLLING ─────────────────────────────────────────────────────────
@app.route("/progress/<job_id>")
def progress(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status":   job["status"],
        "progress": job["progress"],
        "total":    job["total"],
        "error":    job.get("error"),
    })

# ── FILE DOWNLOAD ─────────────────────────────────────────────────────────────
@app.route("/download/<job_id>")
def download(job_id):
    with jobs_lock:
        job = jobs.pop(job_id, None)   # remove from memory after download
    if not job or job["status"] != "done":
        return jsonify({"error": "Not ready or not found"}), 400

    return send_file(
        BytesIO(job["content"]),
        as_attachment=True,
        download_name=job["filename"],
        mimetype="application/xml",
    )

# ── DEV SERVER ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)