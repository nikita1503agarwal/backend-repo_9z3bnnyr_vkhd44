import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson.objectid import ObjectId

from database import db, create_document, get_documents
from schemas import Event, Rsvp

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class EventOut(Event):
    id: str

class RsvpOut(BaseModel):
    id: str
    event_id: str
    user_id: str
    status: str
    user_name: Optional[str] = None

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response

# Utility to convert Mongo docs

def _doc_to_event_out(doc) -> EventOut:
    return EventOut(
        id=str(doc.get("_id")),
        title=doc.get("title"),
        description=doc.get("description"),
        date_iso=doc.get("date_iso"),
        location=doc.get("location"),
        cover_image_url=doc.get("cover_image_url")
    )

# Event endpoints

@app.post("/api/events", response_model=dict)
def create_event(event: Event):
    try:
        event_id = create_document("event", event)
        return {"id": event_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/events/{event_id}", response_model=EventOut)
def get_event(event_id: str):
    try:
        # fetch one by id
        from bson import ObjectId as _ObjectId
        doc = db["event"].find_one({"_id": _ObjectId(event_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Event not found")
        return _doc_to_event_out(doc)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# RSVP endpoints

class RsvpRequest(BaseModel):
    status: str  # "going" or "not_going"
    user_id: str
    user_name: Optional[str] = None

@app.post("/api/events/{event_id}/rsvp", response_model=RsvpOut)
def set_rsvp(event_id: str, body: RsvpRequest):
    try:
        # Upsert RSVP per user_id per event
        coll = db["rsvp"]
        existing = coll.find_one({"event_id": event_id, "user_id": body.user_id})
        data = {
            "event_id": event_id,
            "user_id": body.user_id,
            "status": body.status,
            "user_name": body.user_name,
        }
        if existing:
            coll.update_one({"_id": existing["_id"]}, {"$set": data})
            rsvp_id = str(existing["_id"])
        else:
            rsvp_id = create_document("rsvp", data)
        return RsvpOut(id=rsvp_id, **data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/events/{event_id}/rsvp/{user_id}", response_model=RsvpOut)
def get_my_rsvp(event_id: str, user_id: str):
    try:
        doc = db["rsvp"].find_one({"event_id": event_id, "user_id": user_id})
        if not doc:
            raise HTTPException(status_code=404, detail="No RSVP yet")
        return RsvpOut(
            id=str(doc.get("_id")),
            event_id=doc.get("event_id"),
            user_id=doc.get("user_id"),
            status=doc.get("status"),
            user_name=doc.get("user_name"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/events/{event_id}/counts", response_model=dict)
def get_counts(event_id: str):
    try:
        going = db["rsvp"].count_documents({"event_id": event_id, "status": "going"})
        not_going = db["rsvp"].count_documents({"event_id": event_id, "status": "not_going"})
        return {"going": going, "not_going": not_going}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
