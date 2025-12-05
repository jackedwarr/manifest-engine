from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from typing import List, Optional
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

# --- DATABASE ENGINE (The Black Box) ---
DB_NAME = "manifest_audit.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Create a table to store every transaction
    c.execute('''CREATE TABLE IF NOT EXISTS port_calls
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  vessel_name TEXT,
                  voyage_ref TEXT,
                  port_code TEXT,
                  timestamp TEXT,
                  status TEXT)''')
    conn.commit()
    conn.close()

# Initialize DB on startup
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
    return {"system": "MANIFEST", "status": "online", "security": "active", "database": "connected"}

# 1. THE ADAPTER (Writes to DB now)
@app.post("/api/v1/port-call", dependencies=[Depends(get_api_key)])
def submit_port_call(manifest: PortCall):
    # Identify Tribe
    port_map = {"GBLON": "uk_fal5.xml", "SGSIN": "sg_epc.json"}
    template_file = port_map.get(manifest.port_code)
    
    if not template_file:
        log_transaction(manifest.vessel_name, manifest.voyage_reference, manifest.port_code, "FAILED: Unknown Port")
        return {"status": "error", "message": f"No blueprint for {manifest.port_code}"}

    # Render
    template = env.get_template(template_file)
    output_content = template.render(
        vessel_name=manifest.vessel_name,
        voyage_reference=manifest.voyage_reference,
        port_code=manifest.port_code,
        eta=manifest.eta,
        crew_list=manifest.crew_list
    )
    
    # Save File
    output_filename = f"MANIFEST_{manifest.port_code}_{manifest.voyage_reference}"
    output_filename += ".json" if ".json" in template_file else ".xml"
    with open(output_filename, "w") as f:
        f.write(output_content)

    # Log to Black Box
    log_transaction(manifest.vessel_name, manifest.voyage_reference, manifest.port_code, "SUCCESS")

    return {
        "status": "processed",
        "file_ready": output_filename,
        "audit_logged": True
    }

# 2. THE HISTORY (New Feature!)
@app.get("/api/v1/history", dependencies=[Depends(get_api_key)])
def get_history():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM port_calls ORDER BY id DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    
    # Format for JSON
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
