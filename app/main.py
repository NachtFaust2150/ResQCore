import os
import shutil
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from bson import ObjectId

from app.config import UPLOAD_DIR, BASE_DIR
from app.db import get_database, reset_to_seed_data, get_next_incident_id, clamp_hospital_capacities
from app.auth import verify_password, create_access_token, get_current_user, require_roles
from app.models import (
    LoginRequest, LoginResponse, HospitalCapacityUpdate,
    SimHospitalFullRequest, SimRoadBlockRequest, SimRiskIncreaseRequest, SimNewIncidentRequest
)
from app.core.routing import NODES, find_nearest_node
from app.core.risk_model import risk_predictor
from app.core.optimizer import run_plan

app = FastAPI(
    title="ResQCore — AI Disaster Response System",
    description="Dynamic disaster resource allocation, routing, and risk engine.",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files setup
static_dir = os.path.join(BASE_DIR, "static")
os.makedirs(static_dir, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


def clean_mongo_doc(doc):
    if doc is None:
        return doc
    if isinstance(doc, list):
        return [clean_mongo_doc(item) for item in doc]
    if isinstance(doc, dict):
        cleaned = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                cleaned[k] = str(v)
            elif isinstance(v, (dict, list)):
                cleaned[k] = clean_mongo_doc(v)
            else:
                cleaned[k] = v
        return cleaned
    return doc

# --- AUTH ENDPOINTS ---

@app.post("/api/login", response_model=LoginResponse)
def login(req: LoginRequest):
    db = get_database()
    user = db.users.find_one({"username": req.username})
    if not user or not verify_password(user["password_hash"], req.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    token_data = {
        "sub": user["username"],
        "role": user["role"],
        "ref": user.get("ref", ""),
        "display": user.get("display", user["username"])
    }
    token = create_access_token(token_data)

    return {
        "token": token,
        "role": user["role"],
        "ref": user.get("ref", ""),
        "display": user.get("display", user["username"])
    }


# --- SHARED STATE ENDPOINT ---

@app.get("/api/state")
def get_state(current_user: dict = Depends(get_current_user)):
    db = get_database()
    clamp_hospital_capacities(db)

    hospitals = list(db.hospitals.find())
    ambulances = list(db.ambulances.find())
    rescue_teams = list(db.rescue_teams.find())
    roads = list(db.roads.find())
    incidents = list(db.incidents.find())
    assignments = list(db.assignments.find())
    all_events = list(db.events.find().sort("created_at", -1).limit(50))
    settings_docs = list(db.settings.find())
    settings = {s["_id"]: s.get("value") for s in settings_docs}

    user_role = current_user.get("role")
    user_ref = current_user.get("ref", "")

    # Role-based event and risk model filtering
    risk_importances = None
    if user_role == "ADMIN":
        filtered_events = all_events
        risk_importances = risk_predictor.feature_importances
    elif user_role == "HOSPITAL":
        hosp = next((h for h in hospitals if h["_id"] == user_ref), None)
        h_name = hosp["name"] if hosp else user_ref
        filtered_events = [
            e for e in all_events
            if user_ref in e.get("message", "") or h_name in e.get("message", "") or "Hospital" in e.get("message", "")
        ]
    elif user_role == "AMBULANCE":
        amb = next((a for a in ambulances if a["_id"] == user_ref), None)
        a_name = amb["name"] if amb else user_ref
        filtered_events = [
            e for e in all_events
            if user_ref in e.get("message", "") or a_name in e.get("message", "")
        ]
    elif user_role == "RESCUE":
        filtered_events = [
            e for e in all_events
            if "report" in e.get("message", "").lower() or "rescue" in e.get("message", "").lower() or "incident" in e.get("message", "").lower()
        ]
    else:
        filtered_events = all_events

    return clean_mongo_doc({
        "user": current_user,
        "hospitals": hospitals,
        "ambulances": ambulances,
        "rescue_teams": rescue_teams,
        "roads": roads,
        "incidents": incidents,
        "assignments": assignments,
        "events": filtered_events,
        "settings": settings,
        "risk_model_importances": risk_importances,
        "nodes": NODES
    })


# --- FIELD REPORT ENDPOINT (RESCUE ROLE) ---

@app.post("/api/report")
async def create_field_report(
    critical: int = Form(0),
    serious: int = Form(0),
    moderate: int = Form(0),
    notes: str = Form(""),
    lat: float = Form(None),
    lng: float = Form(None),
    photo: UploadFile = File(None),
    current_user: dict = Depends(require_roles(["RESCUE", "ADMIN"]))
):
    if (critical + serious + moderate) < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least 1 victim required (Critical, Serious, or Moderate)"
        )

    db = get_database()

    photo_path = None
    if photo and photo.filename:
        filename = f"{int(datetime.now(timezone.utc).timestamp())}_{photo.filename}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
        photo_path = f"/uploads/{filename}"

    # Map GPS lat/lng to nearest graph node
    mapped_area = find_nearest_node(lat, lng)
    coords = NODES.get(mapped_area, {}).get("coords", [77.5850, 12.9650])
    if lat is None or lng is None:
        lng, lat = coords[0], coords[1]

    inc_id = get_next_incident_id(db)
    incident_doc = {
        "_id": inc_id,
        "location": {"type": "Point", "coordinates": [lng, lat]},
        "area": mapped_area,
        "critical": max(0, critical),
        "serious": max(0, serious),
        "moderate": max(0, moderate),
        "notes": notes,
        "photo_path": photo_path,
        "reported_by": current_user.get("display", "Rescue Team"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "priority": "Pending",
        "priority_score": 0.0,
        "status": "pending"
    }

    db.incidents.insert_one(incident_doc)

    db.events.insert_one({
        "_id": f"EVT_{inc_id}",
        "type": "incident_reported",
        "message": f"New field report {inc_id} by {current_user.get('display')}: {critical} Critical, {serious} Serious, {moderate} Moderate at node {mapped_area}.",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # Trigger automatic re-plan loop
    plan_result = run_plan(db)

    # Get assigned ambulances for toast response
    assigned_ambs = [a["ambulance_id"] for a in db.assignments.find({"incident_id": inc_id})]

    return {
        "status": "success",
        "incident_id": inc_id,
        "assigned_ambulances": assigned_ambs,
        "plan_result": plan_result
    }


# --- HOSPITAL CAPACITY ENDPOINT (HOSPITAL ROLE) ---

@app.patch("/api/hospital/capacity")
def update_hospital_capacity(
    body: HospitalCapacityUpdate,
    current_user: dict = Depends(require_roles(["HOSPITAL"]))
):
    db = get_database()
    h_id = current_user.get("ref")

    hosp = db.hospitals.find_one({"_id": h_id})
    if not hosp:
        raise HTTPException(status_code=404, detail=f"Hospital '{h_id}' not found")

    t_beds = hosp.get("total_beds", 0)
    t_icu = hosp.get("icu_total", 0)

    if body.available_beds < 0 or body.available_beds > t_beds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Available beds ({body.available_beds}) must be between 0 and total beds ({t_beds})"
        )

    if body.icu_available < 0 or body.icu_available > t_icu:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Available ICU beds ({body.icu_available}) must be between 0 and total ICU beds ({t_icu})"
        )

    db.hospitals.update_one(
        {"_id": h_id},
        {"$set": {
            "available_beds": body.available_beds,
            "icu_available": body.icu_available
        }}
    )

    db.events.insert_one({
        "_id": f"EVT_CAP_{int(datetime.now(timezone.utc).timestamp())}",
        "type": "capacity_update",
        "message": f"{hosp['name']} updated available capacity to {body.available_beds}/{t_beds} beds, {body.icu_available}/{t_icu} ICU beds.",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # Trigger automatic re-plan
    plan_result = run_plan(db)

    return {"status": "success", "message": "Capacity updated", "plan_result": plan_result}


# --- SIMULATION ENDPOINTS (ADMIN ROLE ONLY) ---

@app.post("/api/sim/hospital_full")
def sim_hospital_full(
    req: SimHospitalFullRequest = SimHospitalFullRequest(),
    current_user: dict = Depends(require_roles(["ADMIN"]))
):
    db = get_database()
    h_id = req.hospital_id

    hosp = db.hospitals.find_one({"_id": h_id})
    if not hosp:
        raise HTTPException(status_code=404, detail=f"Hospital '{h_id}' not found")

    db.hospitals.update_one(
        {"_id": h_id},
        {"$set": {"available_beds": 0, "icu_available": 0}}
    )

    db.events.insert_one({
        "_id": f"EVT_SIM_FULL_{int(datetime.now(timezone.utc).timestamp())}",
        "type": "simulation",
        "message": f"{hosp['name']} full (0 beds)",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    plan_result = run_plan(db)
    return {"status": "success", "message": f"{hosp['name']} set to full capacity", "plan_result": plan_result}


@app.post("/api/sim/road_block")
def sim_road_block(
    req: SimRoadBlockRequest = SimRoadBlockRequest(),
    current_user: dict = Depends(require_roles(["ADMIN"]))
):
    db = get_database()
    r_id = req.road_id

    road = db.roads.find_one({"_id": r_id})
    if not road:
        raise HTTPException(status_code=404, detail=f"Road '{r_id}' not found")

    new_blocked = 1 if req.blocked is None else req.blocked
    db.roads.update_one({"_id": r_id}, {"$set": {"blocked": new_blocked}})

    db.events.insert_one({
        "_id": f"EVT_SIM_ROAD_{int(datetime.now(timezone.utc).timestamp())}",
        "type": "simulation",
        "message": f"Road {road['name']} ({r_id}) blocked: route recalculated",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    plan_result = run_plan(db)
    return {"status": "success", "message": f"Road {r_id} set to blocked={new_blocked}", "plan_result": plan_result}


@app.post("/api/sim/risk_increase")
def sim_risk_increase(
    req: SimRiskIncreaseRequest = SimRiskIncreaseRequest(),
    current_user: dict = Depends(require_roles(["ADMIN"]))
):
    db = get_database()
    multiplier = req.multiplier

    db.settings.update_one(
        {"_id": "risk_mult"},
        {"$set": {"value": multiplier}},
        upsert=True
    )

    db.events.insert_one({
        "_id": f"EVT_SIM_RISK_{int(datetime.now(timezone.utc).timestamp())}",
        "type": "simulation",
        "message": f"Risk multiplier raised to {multiplier}x",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    plan_result = run_plan(db)
    return {"status": "success", "message": f"Risk multiplier set to {multiplier}", "plan_result": plan_result}


@app.post("/api/sim/new_incident")
def sim_new_incident(
    req: SimNewIncidentRequest = SimNewIncidentRequest(),
    current_user: dict = Depends(require_roles(["ADMIN"]))
):
    db = get_database()

    inc_id = get_next_incident_id(db)
    coords = NODES.get("N3", {}).get("coords", [77.5750, 12.9600])

    incident_doc = {
        "_id": inc_id,
        "location": {"type": "Point", "coordinates": coords},
        "area": "N3",
        "critical": req.critical,
        "serious": req.serious,
        "moderate": req.moderate,
        "notes": req.notes,
        "photo_path": None,
        "reported_by": "Simulation Control",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "priority": "Pending",
        "priority_score": 0.0,
        "status": "pending"
    }

    db.incidents.insert_one(incident_doc)

    db.events.insert_one({
        "_id": f"EVT_{inc_id}",
        "type": "simulation",
        "message": f"New incident {inc_id} reported at Node N3 ({req.critical} Critical, {req.serious} Serious)",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    plan_result = run_plan(db)
    return {"status": "success", "incident_id": inc_id, "plan_result": plan_result}


@app.post("/api/sim/reset")
def sim_reset(current_user: dict = Depends(require_roles(["ADMIN"]))):
    db = get_database()
    reset_to_seed_data(db)
    return {"status": "success", "message": "Database reset to initial demo state"}


# --- FRONTEND ROUTING & SPA ---

@app.get("/")
def read_root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"message": "ResQCore API is running. Static index.html not found."})

@app.get("/{full_path:path}")
def catch_all(full_path: str):
    # If API call not matched, serve index.html for client-side role routing
    if not full_path.startswith("api/") and not full_path.startswith("uploads/"):
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Not Found")
