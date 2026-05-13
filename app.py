from flask import Flask, jsonify, render_template, request, send_file, request, session
import xml.etree.ElementTree as ET
from io import BytesIO
import os
import xmlrpc.client
from nltk.tokenize import wordpunct_tokenize as tokenize
import re
import json

app = Flask(__name__)
app.secret_key = "key"

# Full path to the JSON
RUNTIME_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config_runtime.json")

def load_runtime_config():
    """Carga la configuración dinámica desde config_runtime.json."""
    with open(RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_runtime_config(data):
    """Guarda la configuración dinámica en config_runtime.json."""
    with open(RUNTIME_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

@app.route("/get_settings", methods=["GET"])
def get_settings():
    cfg = load_runtime_config()
    return jsonify(cfg)

@app.route("/update_settings", methods=["POST"])
def update_settings():
    data = request.get_json()

    ip = data.get("ip")
    port = data.get("port")

    if not ip or not port:
        return jsonify({"status": "error", "message": "Invalid data"}), 400

    try:
        port = int(port)
    except ValueError:
        return jsonify({"status": "error", "message": "Port must be a number"}), 400

    cfg = load_runtime_config()
    cfg["RPC_SERVER_IP"] = ip
    cfg["RPC_SERVER_PORT"] = port

    save_runtime_config(cfg)

    return jsonify({"status": "ok"})


# ---------------------------------------------------------
# Utility: Fix spacing around punctuation after detokenizing
# ---------------------------------------------------------
def detokenize(text):
    listLeft = ['.','!','?',',']
    listBoth = ['-','/',"'",]
    listRight = []

    # Remove space before punctuation
    for punct in listLeft:
        text = text.replace(" " + punct, punct)

    # Remove space after punctuation (if needed)
    for punct in listRight:
        text = text.replace(punct + " ", punct)

    # Remove spaces around punctuation that should be tight
    for punct in listBoth:
        text = text.replace(" " + punct + " ", punct)

    return text


# ---------------------------------------------------------
# Convert the text of an event using the selected model
# (tokenize → send to model → detokenize)
# ---------------------------------------------------------
def convertText(text, model):

    # ---------------------------------------------------------
    # Load dynamic configuration from config_runtime.json
    # ---------------------------------------------------------
    cfg = load_runtime_config()
    RPC_SERVER_IP = cfg.get("RPC_SERVER_IP", "localhost")
    RPC_SERVER_PORT = cfg.get("RPC_SERVER_PORT", 6000)
    RPC_TIMEOUT = cfg.get("RPC_TIMEOUT", 10)

    # ---------------------------------------------------------
    # ACTUAL CODE (commented out for now)
    # ---------------------------------------------------------
    # url = f"http://{RPC_SERVER_IP}:{RPC_SERVER_PORT}/RPC2"
    #
    # try:
    #     proxy = xmlrpc.client.ServerProxy(
    #         url,
    #         allow_none=True,
    #         use_datetime=False,
    #         timeout=RPC_TIMEOUT
    #     )
    # except Exception:
    #     return None, "[ERROR] Cannot connect to RPC server"
    # ---------------------------------------------------------

    # Since the connection is established, there are no server errors
    lines = text.split('\n')
    results = ""

    # ---------------------------------------------------------
    # MODEL 1
    # ---------------------------------------------------------
    if model == "model1":
        for line in lines:
            tokens = tokenize(line)
            line_tok = ' '.join(tokens)

            params = {
                "text": line_tok,
                "align": "false",
                "report-all-factors": "false",
                "model": model,
            }

            # Actual call (when the server exists)
            # result = proxy.translate(params)['text']

            # Temporary simulation
            result = line_tok.upper()

            result = detokenize(result)
            results += result + "\n"

        return results.rstrip("\n"), None

    # ---------------------------------------------------------
    # MODEL 2
    # ---------------------------------------------------------
    elif model == "model2":
        for line in lines:
            tokens = tokenize(line)
            line_tok = ' '.join(tokens)

            params = {
                "text": line_tok,
                "align": "false",
                "report-all-factors": "false"
            }

            # Actual call (when the server exists)
            # result = proxy.translate(params)['text']

            # Temporary simulation
            result = f"[SIMULATED_MODEL_2] {line_tok}"

            result = detokenize(result)
            results += result + "\n"

        return results.rstrip("\n"), None

    # ---------------------------------------------------------
    # Unknown model
    # ---------------------------------------------------------
    return None, "[ERROR] Unknown model selected"


# ---------------------------------------------------------
# Helper: Find the parent element of a given XML node
# ---------------------------------------------------------
def find_parent(root, child):
    for parent in root.iter():
        for elem in list(parent):
            if elem is child:
                return parent
    return None


# ---------------------------------------------------------
# Main route: upload -> process -> return converted EXB/XML
# ---------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():

    # ---------------------------------------------------------
    # GET -> Show blank page (no file; template will be loaded if you wish)
    # ---------------------------------------------------------
    if request.method == "GET":
        selected_model = session.get("selected_model")
        return render_template("index.html", selected_model=selected_model)

    # ---------------------------------------------------------
    # POST -> process conversion
    # ---------------------------------------------------------
    uploaded_file = request.files.get("file")
    model = request.form.get("model")

    session["selected_model"] = model

    # Validation: mandatory model
    if not model:
        return render_template("index.html",
                               error="Please select a model before converting.",
                               selected_model=model)

    # Validation: mandatory file
    if not uploaded_file or uploaded_file.filename == "":
        return render_template("index.html",
                               error="No files have been sent.",
                               selected_model=model)

    # Read the original file
    file_bytes = uploaded_file.read()
    file_text = file_bytes.decode("utf-8")

    # Parse XML/EXB
    try:
        tree = ET.ElementTree(ET.fromstring(file_bytes))
    except ET.ParseError as e:
        return render_template("index.html",
                               error=f"Parsing error: the file is not well‑formed XML/EXB ({str(e)})",
                               selected_model=model)

    root = tree.getroot()
    tiers = list(root.iter("tier"))
    final_text = file_text

    # ---------------------------------------------------------
    # Process each tier
    # ---------------------------------------------------------
    for tier in tiers:

        cat = tier.attrib.get("category", "")
        typ = tier.attrib.get("type", "")

        if not (cat == "v" and typ == "t"):
            continue

        tier_id = tier.attrib.get("id")
        if not tier_id:
            continue

        original_attrib = tier.attrib.copy()

        new_tier = ET.Element("tier", original_attrib)
        new_tier.set("category", "norm")
        new_tier.set("type", "t")
        new_tier.set("id", tier_id + "_norm")

        # Process events
        for event in tier.findall("event"):
            new_event = ET.Element("event", event.attrib)
            original_text = event.text or ""

            # Secure conversion
            converted, error = convertText(original_text, model)

            if error:
                # Cancel conversion and display an error message
                return render_template("index.html",
                                       error=error,
                                       selected_model=model)

            new_event.text = converted
            new_event.tail = "\n"
            new_tier.append(new_event)

        # Convert tier_norm to text
        tier_norm_text = ET.tostring(new_tier, encoding="unicode") + "\n"

        # Insert before the original tier
        pattern = rf'<tier[^>]*\bid="{re.escape(tier_id)}"[^>]*>'
        match = re.search(pattern, final_text)

        if match:
            pos = match.start()
            final_text = final_text[:pos] + tier_norm_text + final_text[pos:]

            # Modify attributes of the original tier
            tier_tag = match.group(0)
            tier_tag_modified = tier_tag
            tier_tag_modified = re.sub(r'category="v"', 'category="colloq"', tier_tag_modified)
            tier_tag_modified = re.sub(r'type="t"', 'type="a"', tier_tag_modified)

            final_text = final_text.replace(tier_tag, tier_tag_modified)

    # ---------------------------------------------------------
    # Prepare the final file for download
    # ---------------------------------------------------------
    output = BytesIO()
    output.write(final_text.encode("utf-8"))
    output.seek(0)

    original_name = os.path.splitext(uploaded_file.filename)[0]
    original_ext = os.path.splitext(uploaded_file.filename)[1]
    download_name = f"{original_name}_converted{original_ext}"

    return send_file(
        output,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/xml"
    )



# ---------------------------------------------------------
# Run Flask development server
# ---------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
