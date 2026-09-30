
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import database

app = FastAPI(title="Meghalaya PHC Care")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

database.init_db()



class ToggleResponse(BaseModel):
    phc_id: int
    status: str


@app.get("/api/status/{village_name}")
def get_status(village_name: str):
    """
    Main chatbot endpoint: takes whatever the user typed, fuzzy-matches
    it against known PHCs, and returns the current doctor status.
    """
    result = database.find_status_by_village(village_name)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No PHC found matching '{village_name}'. Try a nearby town or check the spelling.",
        )
    return result


@app.get("/api/phcs")
def list_phcs():
    """Powers the admin/monitor panel: every PHC with its latest status."""
    return database.get_all_phcs_with_status()


@app.post("/api/toggle/{phc_id}", response_model=ToggleResponse)
def toggle(phc_id: int):
    """
    Flips one PHC's status. Stands in for a doctor's phone
    auto-connecting to (or dropping off) the clinic Wi-Fi.
    """
    try:
        return database.toggle_status(phc_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))



app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_index():
    return FileResponse("static/index.html")
