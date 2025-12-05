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
from datetime import datetime

app = FastAPI(title="MANIFEST: The Universal Adapter (IRONCLAD)")

# --- CONFIG & DATABASE ---
API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
env = Environment(loader=FileSystemLoader("templates"))
DB_NAME = "manifest_audit.db"

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

# --- GLOBAL PORT DATABASE (FULL ARSENAL) ---
PORT_DATABASE = {
    # THE DIVAS (Custom Templates)
    "GBLON": {"name": "London (UK)", "template": "uk_fal5.xml"},
    "SGSIN": {"name": "Singapore (SG)", "template": "sg_epc.json"},
    
    # THE GIANTS (Mapped to Standard IMO Fallback)
    "CNSHA": {"name": "Shanghai (China)", "template": "generic_fal.xml"},
    "CNNBG": {"name": "Ningbo-Zhoushan (China)", "template": "generic_fal.xml"},
    "CNSZX": {"name": "Shenzhen (China)", "template": "generic_fal.xml"},
    "CNCAN": {"name": "Guangzhou (China)", "template": "generic_fal.xml"},
    "KRPUS": {"name": "Busan (South Korea)", "template": "generic_fal.xml"},
    "CNQDG": {"name": "Qingdao (China)", "template": "generic_fal.xml"},
    "HKHKG": {"name": "Hong Kong (HK)", "template": "generic_fal.xml"},
    "CNTSN": {"name": "Tianjin (China)", "template": "generic_fal.xml"},
    "NLRTM": {"name": "Rotterdam (Netherlands)", "template": "generic_fal.xml"},
    "AEDXB": {"name": "Dubai (UAE)", "template": "generic_fal.xml"},
    "MYPKG": {"name": "Port Klang (Malaysia)", "template": "generic_fal.xml"},
    "BEANT": {"name": "Antwerp (Belgium)", "template": "generic_fal.xml"},
    "CNXAM": {"name": "Xiamen (China)", "template": "generic_fal.xml"},
    "USLAX": {"name": "Los Angeles (USA)", "template": "generic_fal.xml"},
    "MYPTP": {"name": "Tanjung Pelepas (Malaysia)", "template": "generic_fal.xml"},
    "TWKHH": {"name": "Kaohsiung (Taiwan)", "template": "generic_fal.xml"},
    "USLGB": {"name": "Long Beach (USA)", "template": "generic_fal.xml"},
    "DEHAM": {"name": "Hamburg (Germany)", "template": "generic_fal.xml"},
    "USNYC": {"name": "New York / NJ (USA)", "template": "generic_fal.xml"},
    "THLCH": {"name": "Laem Chabang (Thailand)", "template": "generic_fal.xml"},
    "VNSGN": {"name": "Ho Chi Minh City (Vietnam)", "template": "generic_fal.xml"},
    "LKCMB": {"name": "Colombo (Sri Lanka)", "template": "generic_fal.xml"},
    "MAPTM": {"name": "Tanger Med (Morocco)", "template": "generic_fal.xml"},
    "IDJKT": {"name": "Jakarta (Indonesia)", "template": "generic_fal.xml"},
    "INMUN": {"name": "Mundra (India)", "template": "generic_fal.xml"},
    "INNSA": {"name": "Nhava Sheva (India)", "template": "generic_fal.xml"},
    "JPTYO": {"name": "Tokyo (Japan)", "template": "generic_fal.xml"},
    "JPYOK": {"name": "Yokohama (Japan)", "template": "generic_fal.xml"},
    "ESVLC": {"name": "Valencia (Spain)", "template": "generic_fal.xml"},
    "ESALG": {"name": "Algeciras (Spain)", "template": "generic_fal.xml"},
    "VNVUT": {"name": "Cai Mep (Vietnam)", "template": "generic_fal.xml"},
    "PHMNL": {"name": "Manila (Philippines)", "template": "generic_fal.xml"},
    "BRSSZ": {"name": "Santos (Brazil)", "template": "generic_fal.xml"},
    "SADMM": {"name": "Dammam (Saudi Arabia)", "template": "generic_fal.xml"},
    "TRMER": {"name": "Mersin (Turkey)", "template": "generic_fal.xml"},
    "GRPIR": {"name": "Piraeus (Greece)", "template": "generic_fal.xml"},
    "USSAV": {"name": "Savannah (USA)", "template": "generic_fal.xml"},
    "ITGOA": {"name": "Genoa (Italy)", "template": "generic_fal.xml"},
    "FRLEH": {"name": "Le Havre (France)", "template": "generic_fal.xml"},
    "GBSOU": {"name": "Southampton (UK)", "template": "uk_fal5.xml"},
    "GBFXT": {"name": "Felixstowe (UK)", "template": "uk_fal5.xml"},
    "GBLIV": {"name": "Liverpool (UK)", "template": "uk_fal5.xml"},
    "CAVAN": {"name": "Vancouver (Canada)", "template": "generic_fal.xml"},
    "AUMEL": {"name": "Melbourne (Australia)", "template": "generic_fal.xml"},
    "AUBNE": {"name": "Brisbane (Australia)", "template": "generic_fal.xml"},
    "ZADUR": {"name": "Durban (South Africa)", "template": "generic_fal.xml"},
    "PABLB": {"name": "Balboa (Panama)", "template": "generic_fal.xml"},
    "MXMAN": {"name": "Manzanillo (Mexico)", "template": "generic_fal.xml"}
}

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"system": "MANIFEST", "status": "online", "mode": "Ironclad Edition"}

# 1. THE ENGINE
def process_manifest(manifest: PortCall):
    # Lookup Port or Fallback to Generic
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

# 2. THE UI
@app.get("/upload", response_class=HTMLResponse)
def upload_page():
    options_html = ""
    # Sorted list of all 50+ ports
    for code, info in sorted(PORT_DATABASE.items(), key=lambda x: x[1]['name']):
        options_html += f'<option value="{code}">{info["name"]} ({code})</option>'

    return f"""
    <html>
        <head>
            <title>MANIFEST | Upload</title>
            <style>
                body {{ background-color: #0a0a0a; color: #fff; font-family: 'Courier New', monospace; padding: 40px; display: flex; justify-content: center; }}
                .form-card {{ background: #1a1a1a; padding: 30px; width: 500px; border: 1px solid #444; }}
                h2 {{ color: #d4af37; border-bottom: 2px solid #d4af37; padding-bottom: 15px; }}
                label {{ display: block; margin-top: 20px; color: #888; font-size: 12px; font-weight: bold; }}
                input, select {{ width: 100%; background: #000; border: 1px solid #333; color: #00ff00; padding: 12px; margin-top: 5px; font-family: 'Courier New', monospace; }}
                button {{ width: 100%; background: #d4af37; color: #000; border: none; padding: 15px; margin-top: 30px; font-weight: bold; cursor: pointer; }}
            </style>
        </head>
        <body>
            <div class="form-card">
                <h2>FILE UPLOAD</h2>
                <form action="/submit-form" method="post" enctype="multipart/form-data">
                    <label>SELECT DESTINATION PORT</label>
                    <select name="port_code">
                        {options_html}
                        <option value="OTHER">--- Manual / Other ---</option>
                    </select>
                    
                    <label>UPLOAD CREW LIST (.xlsx, .csv, .json)</label>
                    <input type="file" name="file" accept=".json,.xlsx,.csv" required>
                    <div style="font-size:10px; color:#555; margin-top:5px;">Supports: Excel, CSV, JSON</div>
                    
                    <button type="submit">PROCESS FILE</button>
                </form>
            </div>
        </body>
    </html>
    """

# 3. THE FORM HANDLER (Reads EXCEL + CSV + JSON)
@app.post("/submit-form", response_class=HTMLResponse)
async def handle_form(port_code: str = Form(...), file: UploadFile = File(...)):
    filename = file.filename
    content = await file.read()
    
    # Defaults
    vessel_name = "MAERSK UNIVERSAL"
    voyage_ref = "VOY-UNIV-001"
    crew_list = []

    try:
        # LOGIC SWITCH: JSON vs EXCEL vs CSV
        if filename.endswith(".json"):
            data = json.loads(content)
            crew_list = data.get("crew_list", [])
            vessel_name = data.get("vessel_name", vessel_name)
        
        elif filename.endswith(".xlsx"):
            # EXCEL HANDLER
            df = pd.read_excel(io.BytesIO(content))
            for index, row in df.iterrows():
                crew_list.append({
                    "family_name": str(row.get('Surname', row.get('FamilyName', 'Unknown'))),
                    "rank": str(row.get('Rank', 'Crew')),
                    "passport": str(row.get('Passport', row.get('DocID', 'X00000'))),
                    "nationality": str(row.get('Nationality', 'Unknown'))
                })
        
        elif filename.endswith(".csv"):
            # CSV HANDLER (The New Addition)
            df = pd.read_csv(io.BytesIO(content))
            for index, row in df.iterrows():
                crew_list.append({
                    "family_name": str(row.get('Surname', row.get('FamilyName', 'Unknown'))),
                    "rank": str(row.get('Rank', 'Crew')),
                    "passport": str(row.get('Passport', row.get('DocID', 'X00000'))),
                    "nationality": str(row.get('Nationality', 'Unknown'))
                })
                
    except Exception as e:
        return f"<h1 style='color:red'>ERROR READING FILE: {str(e)}</h1>"
            
    # CONVERT TO INTERNAL OBJECT
    call_data = PortCall(
        vessel_name=vessel_name,
        voyage_reference=voyage_ref,
        port_code=port_code,
        eta="2025-01-01",
        crew_list=crew_list
    )
    
    # RUN ENGINE
    result = process_manifest(call_data)
    
    return f"""
    <body style="background:#000; color:#fff; font-family:'Courier New'; text-align:center; padding-top:100px;">
        <h1 style="color:#00ff00; border: 2px solid #00ff00; display:inline-block; padding: 10px;">SUCCESS</h1>
        <p>Processed File: {filename}</p>
        <p>Crew Members Extracted: {len(crew_list)}</p>
        <p>Output: {result['file_ready']}</p>
        <br>
        <a href="/dashboard" style="color:#000; background: #d4af37; text-decoration:none; padding:15px 30px; font-weight:bold;">OPEN DASHBOARD</a>
    </body>
    """

# 4. DASHBOARD & DOWNLOADER
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

    html_content = f"""
    <html>
        <head>
            <title>MANIFEST COMMAND</title>
            <style>
                body {{ background-color: #0a0a0a; color: #e0e0e0; font-family: 'Courier New', monospace; padding: 40px; }}
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
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </body>
    </html>
    """
    return html_content

@app.get("/download/{filename}")
def download_file(filename: str):
    if os.path.exists(filename):
        return FileResponse(filename, filename=filename)
    return {"error": "File not found"}
