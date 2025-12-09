from fastapi import FastAPI, HTTPException, Security, Depends, Request, Form, UploadFile, File
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List
from jinja2 import Environment, FileSystemLoader
import os
import sqlite3
import json
import pandas as pd
import io
import re
import requests  # <--- DIRECT CONNECTION
import base64    # <--- IMAGE ENCODING
from datetime import datetime

app = FastAPI(title="MANIFEST: The Global Standardiser")

# --- CONFIG & DATABASE ---
env = Environment(loader=FileSystemLoader("templates"))
DB_NAME = "manifest_audit.db"

# --- API KEY SETUP ---
RAW_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_KEY = RAW_KEY.strip().strip('"').strip("'")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS port_calls
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  vessel_name TEXT,
                  voyage_ref TEXT,
                  port_code TEXT,
                  timestamp TEXT,
                  status TEXT,
                  file_path TEXT)''')
    conn.commit()
    conn.close()

init_db()

def log_transaction(vessel, voyage, port, status, file_path=""):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO port_calls (vessel_name, voyage_ref, port_code, timestamp, status, file_path) VALUES (?, ?, ?, ?, ?, ?)",
              (vessel, voyage, port, timestamp, status, file_path))
    conn.commit()
    conn.close()

# --- MODELS ---
class CrewMember(BaseModel):
    family_name: str
    rank: str
    passport: str
    nationality: str

class PortCall(BaseModel):
    voyage_reference: str
    vessel_name: str
    port_code: str
    eta: str
    crew_list: List[CrewMember]

# --- GLOBAL PORT DATABASE (FULL 60+ HUBS) ---
PORT_DATABASE = {
    # --- UK & EUROPE ---
    "GBLON": {"name": "London (UK)", "template": "uk_fal5.xml"},
    "GBSOU": {"name": "Southampton (UK)", "template": "uk_fal5.xml"},
    "GBFXT": {"name": "Felixstowe (UK)", "template": "uk_fal5.xml"},
    "GBIMM": {"name": "Immingham (UK)", "template": "uk_fal5.xml"},
    "GBHUL": {"name": "Hull (UK)", "template": "uk_fal5.xml"},
    "GBLIV": {"name": "Liverpool (UK)", "template": "uk_fal5.xml"},
    "GBTEE": {"name": "Teesport (UK)", "template": "uk_fal5.xml"},
    "GBGRG": {"name": "Grangemouth (UK)", "template": "uk_fal5.xml"},
    "NLRTM": {"name": "Rotterdam (Netherlands)", "template": "generic_fal.xml"},
    "BEANT": {"name": "Antwerp (Belgium)", "template": "generic_fal.xml"},
    "DEHAM": {"name": "Hamburg (Germany)", "template": "generic_fal.xml"},
    "DEBRE": {"name": "Bremerhaven (Germany)", "template": "generic_fal.xml"},
    "FRLEH": {"name": "Le Havre (France)", "template": "generic_fal.xml"},
    "FRFOS": {"name": "Fos-sur-Mer (France)", "template": "generic_fal.xml"},
    "ESALG": {"name": "Algeciras (Spain)", "template": "generic_fal.xml"},
    "ESVAL": {"name": "Valencia (Spain)", "template": "generic_fal.xml"},
    "ESBCN": {"name": "Barcelona (Spain)", "template": "generic_fal.xml"},
    "ITGOA": {"name": "Genoa (Italy)", "template": "generic_fal.xml"},
    "ITGIO": {"name": "Gioia Tauro (Italy)", "template": "generic_fal.xml"},
    "GRPIR": {"name": "Piraeus (Greece)", "template": "generic_fal.xml"},
    "MTMAR": {"name": "Marsaxlokk (Malta)", "template": "generic_fal.xml"},
    
    # --- ASIA ---
    "SGSIN": {"name": "Singapore (SG)", "template": "sg_epc.json"},
    "CNSHA": {"name": "Shanghai (China)", "template": "generic_fal.xml"},
    "CNNGB": {"name": "Ningbo (China)", "template": "generic_fal.xml"},
    "CNXAM": {"name": "Xiamen (China)", "template": "generic_fal.xml"},
    "CNSZX": {"name": "Shenzhen (China)", "template": "generic_fal.xml"},
    "CNQIN": {"name": "Qingdao (China)", "template": "generic_fal.xml"},
    "CNTSN": {"name": "Tianjin (China)", "template": "generic_fal.xml"},
    "HKHKG": {"name": "Hong Kong (HK)", "template": "generic_fal.xml"},
    "KRBUS": {"name": "Busan (South Korea)", "template": "generic_fal.xml"},
    "KRINC": {"name": "Incheon (South Korea)", "template": "generic_fal.xml"},
    "TWKHH": {"name": "Kaohsiung (Taiwan)", "template": "generic_fal.xml"},
    "JPTYO": {"name": "Tokyo (Japan)", "template": "generic_fal.xml"},
    "JPYOK": {"name": "Yokohama (Japan)", "template": "generic_fal.xml"},
    "JPKOB": {"name": "Kobe (Japan)", "template": "generic_fal.xml"},
    "MYPKG": {"name": "Port Klang (Malaysia)", "template": "generic_fal.xml"},
    "MYTPP": {"name": "Tanjung Pelepas (Malaysia)", "template": "generic_fal.xml"},
    "IDJKT": {"name": "Jakarta (Indonesia)", "template": "generic_fal.xml"},
    "THLCH": {"name": "Laem Chabang (Thailand)", "template": "generic_fal.xml"},
    "VNSGN": {"name": "Ho Chi Minh City (Vietnam)", "template": "generic_fal.xml"},
    "INMUN": {"name": "Mundra (India)", "template": "generic_fal.xml"},
    "INNSA": {"name": "Nhava Sheva (India)", "template": "generic_fal.xml"},
    "INMAA": {"name": "Chennai (India)", "template": "generic_fal.xml"},
    "LKCMB": {"name": "Colombo (Sri Lanka)", "template": "generic_fal.xml"},
    "PHMNL": {"name": "Manila (Philippines)", "template": "generic_fal.xml"},

    # --- MIDDLE EAST & AFRICA ---
    "AEDXB": {"name": "Dubai (UAE)", "template": "generic_fal.xml"},
    "AEJEA": {"name": "Jebel Ali (UAE)", "template": "generic_fal.xml"},
    "AEKHL": {"name": "Khalifa Port (UAE)", "template": "generic_fal.xml"},
    "OMSLL": {"name": "Salalah (Oman)", "template": "generic_fal.xml"},
    "SAJED": {"name": "Jeddah (Saudi Arabia)", "template": "generic_fal.xml"},
    "SADMM": {"name": "Dammam (Saudi Arabia)", "template": "generic_fal.xml"},
    "MAPTM": {"name": "Tanger Med (Morocco)", "template": "generic_fal.xml"},
    "EGPSD": {"name": "Port Said (Egypt)", "template": "generic_fal.xml"},
    "EGPSK": {"name": "Suez (Egypt)", "template": "generic_fal.xml"},
    "ZADUR": {"name": "Durban (South Africa)", "template": "generic_fal.xml"},
    "ZACPT": {"name": "Cape Town (South Africa)", "template": "generic_fal.xml"},
    "NGAPP": {"name": "Apapa/Lagos (Nigeria)", "template": "generic_fal.xml"},

    # --- AMERICAS ---
    "USLAX": {"name": "Los Angeles (USA)", "template": "generic_fal.xml"},
    "USLGB": {"name": "Long Beach (USA)", "template": "generic_fal.xml"},
    "USNYC": {"name": "New York / NJ (USA)", "template": "generic_fal.xml"},
    "USSAV": {"name": "Savannah (USA)", "template": "generic_fal.xml"},
    "USHOU": {"name": "Houston (USA)", "template": "generic_fal.xml"},
    "USSEA": {"name": "Seattle (USA)", "template": "generic_fal.xml"},
    "CAVAN": {"name": "Vancouver (Canada)", "template": "generic_fal.xml"},
    "CAMTR": {"name": "Montreal (Canada)", "template": "generic_fal.xml"},
    "MXMAN": {"name": "Manzanillo (Mexico)", "template": "generic_fal.xml"},
    "PABLB": {"name": "Balboa (Panama)", "template": "generic_fal.xml"},
    "PAONX": {"name": "Colon (Panama)", "template": "generic_fal.xml"},
    "BRSSZ": {"name": "Santos (Brazil)", "template": "generic_fal.xml"},
    "BRRIO": {"name": "Rio de Janeiro (Brazil)", "template": "generic_fal.xml"},
    "ARPZA": {"name": "Buenos Aires (Argentina)", "template": "generic_fal.xml"},
    "CLSAI": {"name": "San Antonio (Chile)", "template": "generic_fal.xml"},
    "PECLL": {"name": "Callao (Peru)", "template": "generic_fal.xml"},
    
    # --- OCEANIA ---
    "AUMEL": {"name": "Melbourne (Australia)", "template": "generic_fal.xml"},
    "AUBNE": {"name": "Brisbane (Australia)", "template": "generic_fal.xml"},
    "AUSYD": {"name": "Sydney (Australia)", "template": "generic_fal.xml"},
    "AUFRE": {"name": "Fremantle (Australia)", "template": "generic_fal.xml"},
    "NZAKL": {"name": "Auckland (New Zealand)", "template": "generic_fal.xml"},
    "NZTRG": {"name": "Tauranga (New Zealand)", "template": "generic_fal.xml"}
}

# --- ENDPOINTS ---
@app.get("/")
def home():
    return {"system": "MANIFEST", "status": "online", "mode": "Universal Auto-Negotiator"}

# 1. THE ENGINE (XML Generator)
def process_manifest(manifest: PortCall):
    port_info = PORT_DATABASE.get(manifest.port_code)
    template_file = port_info["template"] if port_info else "generic_fal.xml"
    
    template = env.get_template(template_file)
    output_content = template.render(
        vessel_name=manifest.vessel_name,
        voyage_reference=manifest.voyage_reference,
        port_code=manifest.port_code,
        eta=manifest.eta,
        crew_list=manifest.crew_list
    )
    
    output_filename = f"MANIFEST_{manifest.port_code}_{manifest.voyage_reference}"
    output_filename += ".json" if ".json" in template_file else ".xml"
        
    with open(output_filename, "w") as f:
        f.write(output_content)

    log_transaction(manifest.vessel_name, manifest.voyage_reference, manifest.port_code, "SUCCESS", output_filename)
    return {"file_ready": output_filename, "standard_used": template_file}

# 2. THE BRAIN (UNIVERSAL AUTO-NEGOTIATOR)
def extract_with_ai(content, mime_type):
    if not GEMINI_KEY:
        print("DEBUG: API Key missing")
        return {"crew_list": []}

    # STEP A: ASK GOOGLE WHAT MODELS ARE AVAILABLE
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}"
    chosen_model = None

    try:
        print("DEBUG: Negotiating model list...")
        list_resp = requests.get(list_url)
        
        if list_resp.status_code != 200:
            print(f"DEBUG: ListModels Failed: {list_resp.text}")
            # Fallback to a safe default if list fails
            chosen_model = "models/gemini-1.5-flash"
        else:
            data = list_resp.json()
            # Find the first model that supports 'generateContent'
            for m in data.get('models', []):
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    name = m['name'] # e.g. models/gemini-1.5-flash
                    print(f"DEBUG: Found available model: {name}")
                    # Prioritize Flash or Pro, but take anything
                    if 'flash' in name or 'pro' in name:
                        chosen_model = name
                        break
            
            if not chosen_model and data.get('models'):
                chosen_model = data['models'][0]['name']
                
    except Exception as e:
        print(f"DEBUG: Negotiation Error: {e}")
        chosen_model = "models/gemini-1.5-flash"

    print(f"DEBUG: LOCKED ON TARGET MODEL: {chosen_model}")

    # STEP B: EXECUTE WITH CHOSEN MODEL
    # chosen_model already contains "models/..." prefix usually
    if not chosen_model.startswith("models/"):
        chosen_model = f"models/{chosen_model}"

    url = f"https://generativelanguage.googleapis.com/v1beta/{chosen_model}:generateContent?key={GEMINI_KEY}"
    
    b64_data = base64.b64encode(content).decode('utf-8')
    
    prompt_text = """
    Extract crew data from this image.
    Return ONLY a valid JSON object.
    The root key must be "crew_list".
    Schema:
    {
      "crew_list": [
        {"family_name": "Str", "rank": "Str", "passport": "Str", "nationality": "Str"}
      ]
    }
    If data is illegible, use "UNKNOWN".
    """
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt_text},
                {"inline_data": {
                    "mime_type": mime_type,
                    "data": b64_data
                }}
            ]
        }]
    }

    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        
        if response.status_code != 200:
             print(f"DEBUG: AI Execution Failed: {response.text}")
             return {"crew_list": []}
             
        response_json = response.json()
        ai_text = response_json['candidates'][0]['content']['parts'][0]['text']
        
        # VACUUM CLEANER
        match = re.search(r'\{.*\}', ai_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        
        clean_text = ai_text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)

    except Exception as e:
        print(f"API EXECUTION ERROR: {e}")
        return {"crew_list": []}

# 3. THE UI
@app.get("/upload", response_class=HTMLResponse)
def upload_page():
    options_html = ""
    for code, info in sorted(PORT_DATABASE.items(), key=lambda x: x[1]['name']):
        options_html += f'<option value="{code}">{info["name"]} ({code})</option>'

    return f"""
    <html>
        <head>
            <title>MANIFEST | Command Console</title>
            <style>
                body {{ background-color: #0a0a0a; color: #fff; font-family: monospace; padding: 40px; display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; }}
                .form-card {{ background: #1a1a1a; padding: 40px; width: 600px; border: 1px solid #444; margin-bottom: 50px; }}
                h2 {{ color: #d4af37; border-bottom: 2px solid #d4af37; padding-bottom: 15px; letter-spacing: 2px; margin-top: 0; }}
                label {{ display: block; margin-top: 20px; color: #888; font-size: 11px; font-weight: bold; text-transform: uppercase; }}
                input[type="text"], input[type="datetime-local"], select {{ width: 100%; background: #000; border: 1px solid #333; color: #00ff00; padding: 12px; margin-top: 5px; font-family: monospace; box-sizing: border-box; }}
                .manual-box {{ border-left: 2px solid #d4af37; padding-left: 10px; margin-top: 10px; }}
                .row {{ display: flex; gap: 15px; }}
                .col {{ flex: 1; }}
                .file-upload-wrapper {{ margin-top: 5px; }}
                input[type="file"] {{ width: 100%; padding: 15px; background: #111; border: 2px dashed #555; color: #fff; cursor: pointer; box-sizing: border-box; }}
                input[type="file"]:hover {{ border-color: #d4af37; }}
                button {{ width: 100%; background: #d4af37; color: #000; border: none; padding: 15px; margin-top: 30px; font-weight: bold; cursor: pointer; letter-spacing: 1px; }}
                button:hover {{ background: #fff; }}
                .ai-badge {{ background: #333; color: #00ff00; font-size: 10px; padding: 2px 6px; border-radius: 4px; margin-left: 10px; }}
            </style>
        </head>
        <body>
            <div class="form-card">
                <h2>LOGISTICS COMMAND <span class="ai-badge">AI ACTIVE</span></h2>
                <form action="/submit-form" method="post" enctype="multipart/form-data">
                    <div class="row">
                        <div class="col">
                            <label>Vessel Name</label>
                            <input type="text" name="vessel_name" value="MAERSK GLOBAL" required>
                        </div>
                        <div class="col">
                            <label>Voyage Reference</label>
                            <input type="text" name="voyage_ref" value="VOY-2025-X" required>
                        </div>
                    </div>
                    <label>ETA (UTC)</label>
                    <input type="datetime-local" name="eta" required>
                    <hr style="border: 0; border-top: 1px solid #333; margin: 25px 0;">
                    <label>Destination Port</label>
                    <select name="port_code_select">
                        {options_html}
                        <option value="OTHER">--- MANUAL / OTHER ---</option>
                    </select>
                    <div class="manual-box">
                        <label>Manual Port Code (If 'Other' selected)</label>
                        <input type="text" name="manual_port_code" placeholder="e.g. PKGWA, ERMSW">
                    </div>
                    <hr style="border: 0; border-top: 1px solid #333; margin: 25px 0;">
                    <label>Upload Manifest (PDF, IMG, Excel)</label>
                    <div class="file-upload-wrapper">
                        <input type="file" name="file" accept=".json,.xlsx,.csv,.pdf,.jpg,.png" required>
                    </div>
                    <button type="submit">GENERATE MANIFEST</button>
                </form>
            </div>
        </body>
    </html>
    """

# 4. THE HANDLER
@app.post("/submit-form", response_class=HTMLResponse)
async def handle_form(
    vessel_name: str = Form(...),
    voyage_ref: str = Form(...),
    eta: str = Form(...),
    port_code_select: str = Form(...),
    manual_port_code: str = Form(None),
    file: UploadFile = File(...)
):
    final_port_code = port_code_select
    if port_code_select == "OTHER":
        if not manual_port_code:
            return "<h1 style='color:red'>ERROR: You selected 'OTHER' but didn't type a Port Code.</h1>"
        final_port_code = manual_port_code.upper()

    filename = file.filename
    content = await file.read()
    crew_list = []
    
    # --- ROUTING LOGIC ---
    try:
        if filename.endswith(".json"):
            data = json.loads(content)
            crew_list = data.get("crew_list", [])
        elif filename.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(content))
            for index, row in df.iterrows():
                crew_list.append({
                    "family_name": str(row.get('Surname', row.get('FamilyName', 'Unknown'))),
                    "rank": str(row.get('Rank', 'Crew')),
                    "passport": str(row.get('Passport', row.get('DocID', 'X00000'))),
                    "nationality": str(row.get('Nationality', 'Unknown'))
                })
        elif filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
            for index, row in df.iterrows():
                crew_list.append({
                    "family_name": str(row.get('Surname', 'Unknown')),
                    "rank": str(row.get('Rank', 'Crew')),
                    "passport": str(row.get('Passport', 'X00000')),
                    "nationality": str(row.get('Nationality', 'Unknown'))
                })
        elif filename.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png')):
            # --- AI ACTIVATION (Direct) ---
            mime_type = file.content_type or "application/pdf"
            ai_data = extract_with_ai(content, mime_type)
            crew_list = ai_data.get("crew_list", [])

    except Exception as e:
        return f"<h1 style='color:red'>FILE ERROR: {str(e)}</h1>"

    call_data = PortCall(
        vessel_name=vessel_name,
        voyage_reference=voyage_ref,
        port_code=final_port_code,
        eta=eta,
        crew_list=crew_list
    )
    result = process_manifest(call_data)
    standard_msg = "SPECIALIZED BLUEPRINT"
    if "generic" in result['standard_used']:
        standard_msg = "STANDARD IMO FAL FALLBACK"

    return f"""
    <body style="background:#000; color:#fff; font-family:monospace; text-align:center; padding-top:50px;">
        <h1 style="color:#00ff00; border: 2px solid #00ff00; display:inline-block; padding: 10px;">SUCCESS</h1>
        <div style="background:#111; display:inline-block; padding:20px; text-align:left; border:1px solid #333;">
            <p><strong>VESSEL:</strong> {vessel_name}</p>
            <p><strong>PORT:</strong> {final_port_code}</p>
            <p><strong>FORMAT:</strong> <span style="color:#d4af37">{standard_msg}</span></p>
            <p><strong>CREW COUNT:</strong> {len(crew_list)}</p>
            <p><strong>FILE:</strong> {result['file_ready']}</p>
        </div>
        <br><br>
        <a href="/dashboard" style="color:#000; background: #d4af37; text-decoration:none; padding:15px 30px; font-weight:bold;">OPEN DASHBOARD</a>
    </body>
    """

# 5. DASHBOARD
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM port_calls ORDER BY id DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    table_rows = ""
    for row in rows:
        status_color = "#00ff00" if row[5] == "SUCCESS" else "#ff0000"
        file_link = f"<a href='/download/{row[6]}' style='color:#fff; text-decoration: underline;'>DOWNLOAD</a>" if row[6] else "-"
        table_rows += f"""
        <tr style="border-bottom: 1px solid #333;">
            <td style="padding: 12px;">{row[1]}</td>
            <td style="padding: 12px;">{row[3]}</td>
            <td style="padding: 12px;">{row[4]}</td>
            <td style="padding: 12px; color: {status_color}; font-weight: bold;">{row[5]}</td>
            <td style="padding: 12px;">{file_link}</td>
        </tr>
        """
    return f"""
    <html>
        <head>
            <title>MANIFEST COMMAND</title>
            <style>
                body {{ background-color: #0a0a0a; color: #e0e0e0; font-family: monospace; padding: 40px; }}
                h1 {{ color: #ffffff; letter-spacing: 2px; border-bottom: 2px solid #333; padding-bottom: 10px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th {{ text-align: left; padding: 12px; color: #888; border-bottom: 1px solid #555; }}
                a {{ color: #d4af37; text-decoration: none; }}
                .top-nav {{ margin-bottom: 20px; }}
                .btn {{ background: #d4af37; color: #000; padding: 10px 20px; text-decoration: none; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="top-nav">
                <a href="/upload" class="btn">+ UPLOAD FILE</a>
            </div>
            <h1>MANIFEST <span style="color:#666">LOGISTICS OS</span></h1>
            <table>
                <thead>
                    <tr>
                        <th>VESSEL</th>
                        <th>PORT</th>
                        <th>TIMESTAMP (UTC)</th>
                        <th>STATUS</th>
                        <th>ACTION</th>
                    </tr>
                </thead>
                <tbody>{table_rows}</tbody>
            </table>
        </body>
    </html>
    """

@app.get("/download/{filename}")
def download_file(filename: str):
    if os.path.exists(filename):
        return FileResponse(filename, filename=filename)
    return {"error": "File not found"}
