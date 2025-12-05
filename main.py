from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
from jinja2 import Environment, FileSystemLoader
import os
import sqlite3
from datetime import datetime

app = FastAPI(title="MANIFEST: The Universal Adapter (ENTERPRISE)")

# --- SECURITY ---
API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)
VALID_API_KEYS = ["MANIFEST_MASTER_KEY_007", "MAERSK_LIVE_KEY_888"]

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header in VALID_API_KEYS:
        return api_key_header
    else:
        raise HTTPException(status_code=403, detail="ACCESS DENIED")

# --- DATABASE ENGINE ---
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
                  status TEXT)''')
    conn.commit()
    conn.close()

init_db()

def log_transaction(vessel, voyage, port, status):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO port_calls (vessel_name, voyage_ref, port_code, timestamp, status) VALUES (?, ?, ?, ?, ?)",
              (vessel, voyage, port, timestamp, status))
    conn.commit()
    conn.close()

# --- CONFIG ---
env = Environment(loader=FileSystemLoader("templates"))

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

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"system": "MANIFEST", "status": "online", "mode": "Enterprise"}

# 1. THE ADAPTER
@app.post("/api/v1/port-call", dependencies=[Depends(get_api_key)])
def submit_port_call(manifest: PortCall):
    port_map = {"GBLON": "uk_fal5.xml", "SGSIN": "sg_epc.json"}
    template_file = port_map.get(manifest.port_code)
    
    if not template_file:
        log_transaction(manifest.vessel_name, manifest.voyage_reference, manifest.port_code, "FAILED: Unknown Port")
        return {"status": "error", "message": f"No blueprint for {manifest.port_code}"}

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

    log_transaction(manifest.vessel_name, manifest.voyage_reference, manifest.port_code, "SUCCESS")

    return {"status": "processed", "file_ready": output_filename}

# 2. THE API HISTORY
@app.get("/api/v1/history", dependencies=[Depends(get_api_key)])
def get_history():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM port_calls ORDER BY id DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        history.append({
            "id": row[0],
            "vessel": row[1],
            "voyage": row[2],
            "port": row[3],
            "time": row[4],
            "status": row[5]
        })
    return history

# 3. THE VISUAL DASHBOARD (The New Face)
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM port_calls ORDER BY id DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()

    # Generate HTML Table
    table_rows = ""
    for row in rows:
        status_color = "green" if row[5] == "SUCCESS" else "red"
        table_rows += f"""
        <tr style="border-bottom: 1px solid #333;">
            <td style="padding: 12px;">{row[1]}</td>
            <td style="padding: 12px;">{row[3]}</td>
            <td style="padding: 12px;">{row[4]}</td>
            <td style="padding: 12px; color: {status_color}; font-weight: bold;">{row[5]}</td>
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
                .card {{ background: #111; padding: 20px; border: 1px solid #333; border-radius: 4px; }}
                .status-live {{ color: #00ff00; font-size: 12px; float: right; margin-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>MANIFEST <span style="color:#666">LOGISTICS OS</span> <span class="status-live">● SYSTEM ONLINE</span></h1>
                
                <table>
                    <thead>
                        <tr>
                            <th>VESSEL</th>
                            <th>PORT</th>
                            <th>TIMESTAMP (UTC)</th>
                            <th>STATUS</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows}
                    </tbody>
                </table>
            </div>
        </body>
    </html>
    """
    return html_content
