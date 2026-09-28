"""
app.py
------
FastAPI backend for the Meghalaya PHC Care status bot.

LEARNING NOTE: FastAPI reads your Python type hints and turns them
into request validation AND interactive docs, automatically. Once this
is running, open http://127.0.0.1:8000/docs -- you can test every
endpoint below right there, with no frontend involved. Do that FIRST
when you're debugging, so you always know whether a bug is in your
backend or your frontend.

Run with:
    uvicorn app:app --reload
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import database

app = FastAPI(title="Meghalaya PHC Care")

# CORS: without this, a browser blocks fetch() calls made from your
# HTML page to this API whenever they're on different origins/ports.
# Wide open ("*") is fine for a local hackathon demo -- you'd lock
# this down before ever deploying it for real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

database.init_db()


# Pydantic models describe the exact shape of data going in or out.
# FastAPI uses this both to validate requests and to build the /docs
# page -- one declaration does two jobs.
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


# Serve the frontend. This is mounted AFTER the API routes on purpose:
# FastAPI matches routes in the order they're declared, so /api/...
# always resolves first, and everything else falls through to static
# files.
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_index():
    return FileResponse("static/index.html")
