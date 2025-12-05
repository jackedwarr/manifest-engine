from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from typing import List
from jinja2 import Environment, FileSystemLoader
import os

app = FastAPI(title="MANIFEST: The Universal Adapter (SECURE)")

# --- SECURITY LAYER ---
# We define the Lock. The Client must send a header called "X-API-KEY"
API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

# The Vault of Valid Keys (In real life, this comes from a database)
# For now, we create one Master Key for you.
VALID_API_KEYS = [
    "MANIFEST_MASTER_KEY_007", 
    "MAERSK_LIVE_KEY_888"
]

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header in VALID_API_KEYS:
        return api_key_header
    else:
        raise HTTPException(
            status_code=403, 
            detail="ACCESS DENIED: Invalid Authentication Key"
        )

# --- CONFIGURATION ---
env = Environment(loader=FileSystemLoader("templates"))

# --- DATA MODELS ---
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

# --- WELCOME MAT ---
@app.get("/")
def home():
    return {"system": "MANIFEST", "status": "online", "security": "active"}

# --- THE SECURE ADAPTER ---
# Note the 'dependencies=[Depends(get_api_key)]'. This locks the door.
@app.post("/api/v1/port-call", dependencies=[Depends(get_api_key)])
def submit_port_call(manifest: PortCall):
    
    # 1. IDENTIFY THE TRIBE
    port_map = {
        "GBLON": "uk_fal5.xml",
        "SGSIN": "sg_epc.json"
    }
    
    template_file = port_map.get(manifest.port_code)
    
    if not template_file:
        return {"status": "error", "message": f"No blueprint found for port {manifest.port_code}"}

    # 2. RENDER
    template = env.get_template(template_file)
    output_content = template.render(
        vessel_name=manifest.vessel_name,
        voyage_reference=manifest.voyage_reference,
        port_code=manifest.port_code,
        eta=manifest.eta,
        crew_list=manifest.crew_list
    )
    
    # 3. SAVE
    output_filename = f"MANIFEST_{manifest.port_code}_{manifest.voyage_reference}"
    output_filename += ".json" if ".json" in template_file else ".xml"
        
    with open(output_filename, "w") as f:
        f.write(output_content)

    return {
        "status": "processed",
        "authorized": True,
        "file_ready": output_filename
    }
