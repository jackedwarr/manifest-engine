import os
import json
import re
from flask import Flask, request, render_template, jsonify
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

GENAI_API_KEY = os.getenv("GENAI_API_KEY")
if not GENAI_API_KEY:
    raise ValueError("No API Key found. Please set GENAI_API_KEY in your .env file.")

genai.configure(api_key=GENAI_API_KEY)

# --- THE DCSA STANDARD PROMPT ---
SYSTEM_INSTRUCTION = """
You are a specialized Data Extraction Engine for Global Logistics.
Your job is to read shipping documents and convert them into strict DCSA compliant JSON.

RULES:
1. Output ONLY valid JSON.
2. Follow the exact schema below. If a field is not present, use null.
3. Convert all dates to YYYY-MM-DD.

TARGET JSON STRUCTURE:
{
  "documentMetadata": {
    "type": "BillOfLading | Manifest | TallySheet",
    "scanQuality": "High | Medium | Low"
  },
  "transportDocumentReference": "STRING",
  "issueDate": "YYYY-MM-DD",
  "carrier": {
    "carrierName": "STRING",
    "carrierCode": "STRING (SCAC/SMDG code)"
  },
  "parties": {
    "shipper": { "partyName": "STRING", "address": "STRING" },
    "consignee": { "partyName": "STRING", "address": "STRING" },
    "notifyParty": { "partyName": "STRING", "address": "STRING" }
  },
  "transportLeg": {
      "modeOfTransport": "VESSEL | TRUCK | RAIL",
      "vesselName": "STRING",
      "voyageNumber": "STRING",
      "portOfLoading": "STRING",
      "portOfDischarge": "STRING"
  },
  "consignmentItems": [
    {
      "description": "STRING",
      "hsCode": "STRING",
      "grossWeight": { "value": "FLOAT", "unit": "KGM | LBR" },
      "numberOfPackages": "INTEGER",
      "packageType": "STRING",
      "containerId": "STRING",
      "sealNumber": "STRING"
    }
  ]
}
"""

def clean_json_string(json_string):
    json_string = re.sub(r'```json\s*', '', json_string)
    json_string = re.sub(r'```\s*$', '', json_string)
    return json_string.strip()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        image_data = file.read()
        mime_type = file.mimetype

        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM_INSTRUCTION
        )

        response = model.generate_content([
            {"mime_type": mime_type, "data": image_data},
            "Extract the data from this document into the DCSA JSON format."
        ])

        cleaned_text = clean_json_string(response.text)
        json_data = json.loads(cleaned_text)

        return jsonify(json_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
