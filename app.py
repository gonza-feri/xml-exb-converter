from flask import Flask, render_template, request, send_file
import xml.etree.ElementTree as ET
from io import BytesIO
import os
import xmlrpc.client
from nltk.tokenize import wordpunct_tokenize as tokenize

app = Flask(__name__)

# ---------------------------------------------------------
# Utility: Fix spacing around punctuation after detokenizing
# ---------------------------------------------------------
def detokenize(text):
    # Punctuation rules for spacing adjustments
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
    url = "http://localhost:6000/RPC2"
    proxy = xmlrpc.client.ServerProxy(url)

    lines = text.split('\n')
    results = ""

    for line in lines:
        tokens = tokenize(line)
        line_tok = ' '.join(tokens)
        params = {
            "text": line_tok,
            "align": "false",
            "report-all-factors": "false",
            "model": model,
        }
        # result = proxy.translate(params)['text']
        # Placeholder result while the real server is unavailable:
        result = line_tok.upper()

        result = detokenize(result)
        results += result + "\n"

    return results.rstrip("\n")

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
# Main route: upload → process → return converted EXB/XML
# ---------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    # Retrieve uploaded file and selected model
    uploaded_file = request.files.get("file")
    model = request.form.get("model")

    # Validate file presence
    if not uploaded_file or uploaded_file.filename == "":
        error_message = "No files have been sent."
        return render_template("index.html", error=error_message)

    # Read file content (exact original text preserved)
    file_bytes = uploaded_file.read()
    file_text = file_bytes.decode("utf-8")

    # Parse XML/EXB structure (only for locating tiers)
    try:
        tree = ET.ElementTree(ET.fromstring(file_bytes))
    except ET.ParseError as e:
        error_message = f"Parsing error: the file is not well‑formed XML/EXB ({str(e)})"
        return render_template("index.html", error=error_message)

    root = tree.getroot()

    # Work on a copy of the tier list to avoid iteration issues
    tiers = list(root.iter("tier"))

    # We will progressively insert each new tier_norm into the original text
    final_text = file_text

    for tier in tiers:
        # Only process tiers with category="v" and type="t"
        cat = tier.attrib.get("category", "")
        typ = tier.attrib.get("type", "")

        if not (cat == "v" and typ == "t"):
            continue

        parent = find_parent(root, tier)
        if parent is None:
            continue

        # Copy original tier attributes
        original_attrib = tier.attrib.copy()

        # Create the new "normalized" tier
        new_tier = ET.Element("tier", original_attrib)
        new_tier.set("category", "norm")
        new_tier.set("type", "t")

        # Generate new tier ID
        if "id" in new_tier.attrib:
            new_tier.set("id", new_tier.get("id") + "_norm")
        else:
            new_tier.set("id", "auto_norm")

        # Copy events and replace text with converted version
        for event in tier.findall("event"):
            new_event = ET.Element("event", event.attrib)
            original_text = event.text or ""
            modified_text = convertText(original_text, model)
            new_event.text = modified_text
            # Add newline after each new event (only for added tiers)
            new_event.tail = "\n"
            new_tier.append(new_event)

        # Convert the new tier to text
        tier_norm_text = ET.tostring(new_tier, encoding="unicode")

        # Convert original tier to text (as ElementTree serializes it)
        # This is used ONLY to locate the tier in the original file
        tier_original_text = ET.tostring(tier, encoding="unicode")

        # Find the position of the original tier in the original file
        pos = final_text.find(tier_original_text)

        if pos != -1:
            # Insert the new tier_norm immediately before the original tier
            final_text = final_text[:pos] + tier_norm_text + final_text[pos:]
            # Modify the original tier
            final_text = final_text.replace(
                tier_original_text,
                tier_original_text.replace('category="v"', 'category="colloq"').replace('type="t"', 'type="a"')
            )

    # ---------------------------------------------------------
    # Prepare file for download (original + inserted tiers)
    # ---------------------------------------------------------
    output = BytesIO()
    output.write(final_text.encode("utf-8"))
    output.seek(0)

    # Build output filename
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
