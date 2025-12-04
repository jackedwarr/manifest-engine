from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from jinja2 import Environment, FileSystemLoader
import os

app = FastAPI(title="MANIFEST: The Universal Adapter")

# --- CONFIGURATION ---
env = Environment(loader=FileSystemLoader("templates"))

# --- THE GOLDEN RECORD (The Data we accept) ---
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

# --- THE ADAPTER ---
@app.post("/api/v1/port-call")
def submit_port_call(manifest: PortCall):
    # 1. IDENTIFY THE TRIBE (Map port code to blueprint)
    port_map = {
        "GBLON": "uk_fal5.xml",
        "SGSIN": "sg_epc.json"
    }
    
    template_file = port_map.get(manifest.port_code)
    
    if not template_file:
        return {"status": "error", "message": f"No blueprint found for port {manifest.port_code}"}

    # 2. LOAD & RENDER
    template = env.get_template(template_file)
    output_content = template.render(
        vessel_name=manifest.vessel_name,
        voyage_reference=manifest.voyage_reference,
        port_code=manifest.port_code,
        eta=manifest.eta,
        crew_list=manifest.crew_list
    )
    
    # 3. SAVE THE FILE
    output_filename = f"MANIFEST_{manifest.port_code}_{manifest.voyage_reference}"
    output_filename += ".json" if ".json" in template_file else ".xml"
        
    with open(output_filename, "w") as f:
        f.write(output_content)

    return {
        "status": "processed",
        "port": manifest.port_code,
        "blueprint_used": template_file,
        "file_ready": output_filename
    }
