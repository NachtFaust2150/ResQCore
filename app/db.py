import os
import pymongo
from datetime import datetime, timezone
from app.config import MONGODB_URI, DB_NAME
from app.auth import hash_password
from app.core.routing import DEFAULT_ROADS, NODES

# Global MongoDB Client & Database references
client = None
db = None

def get_database():
    global client, db
    if db is not None:
        return db

    try:
        # Try real MongoDB connection first
        client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
        # Force a server check
        client.admin.command('ping')
        db = client[DB_NAME]
        print(f"Connected to real MongoDB at {MONGODB_URI}")
    except Exception as e:
        print(f"MongoDB connection failed ({e}). Falling back to in-memory mongomock Database.")
        import mongomock
        client = mongomock.MongoClient()
        db = client[DB_NAME]

    # Ensure 2dsphere indexes on geospatial collections
    _ensure_indexes(db)
    # Seed initial demo state if empty
    _seed_demo_data(db)
    # Clamp any corrupted capacities where available > total
    clamp_hospital_capacities(db)

    return db

def get_next_incident_id(db_inst=None) -> str:
    if db_inst is None:
        db_inst = get_database()
    
    seq_doc = db_inst.settings.find_one({"_id": "inc_seq"})
    if not seq_doc:
        val = 1
        db_inst.settings.insert_one({"_id": "inc_seq", "value": val})
    else:
        val = seq_doc.get("value", 0) + 1
        db_inst.settings.update_one({"_id": "inc_seq"}, {"$set": {"value": val}})

    return f"INC-{val:03d}"

def clamp_hospital_capacities(db_inst=None):
    if db_inst is None:
        db_inst = get_database()
    for h in db_inst.hospitals.find():
        t_beds = h.get("total_beds", 0)
        a_beds = min(h.get("available_beds", 0), t_beds)
        t_icu = h.get("icu_total", 0)
        a_icu = min(h.get("icu_available", 0), t_icu)
        if a_beds != h.get("available_beds") or a_icu != h.get("icu_available"):
            db_inst.hospitals.update_one(
                {"_id": h["_id"]},
                {"$set": {"available_beds": max(0, a_beds), "icu_available": max(0, a_icu)}}
            )

def _ensure_indexes(db_inst):
    collections_with_location = ["hospitals", "ambulances", "rescue_teams", "incidents"]
    for coll_name in collections_with_location:
        try:
            db_inst[coll_name].create_index([("location", pymongo.GEOSPHERE)])
        except Exception:
            # mongomock or silent fallback
            pass

def reset_to_seed_data(db_inst=None):
    if db_inst is None:
        db_inst = get_database()

    # Clear all collections
    db_inst.users.delete_many({})
    db_inst.hospitals.delete_many({})
    db_inst.ambulances.delete_many({})
    db_inst.rescue_teams.delete_many({})
    db_inst.roads.delete_many({})
    db_inst.incidents.delete_many({})
    db_inst.assignments.delete_many({})
    db_inst.events.delete_many({})
    db_inst.settings.delete_many({})

    _seed_demo_data(db_inst)

def _seed_demo_data(db_inst):
    if db_inst.users.count_documents({}) > 0:
        return

    print("Seeding demo data into database...")

    # 1. Users
    users = [
        {"_id": "U_ADMIN", "username": "admin", "password_hash": hash_password("admin123"), "role": "ADMIN", "ref": "ADMIN", "display": "System Coordinator"},
        {"_id": "U_RESCUE1", "username": "rescue1", "password_hash": hash_password("rescue123"), "role": "RESCUE", "ref": "R1", "display": "Rescue Team Alpha"},
        {"_id": "U_AMB1", "username": "amb1", "password_hash": hash_password("amb123"), "role": "AMBULANCE", "ref": "A1", "display": "Ambulance A1 Unit"},
        {"_id": "U_AMB2", "username": "amb2", "password_hash": hash_password("amb123"), "role": "AMBULANCE", "ref": "A2", "display": "Ambulance A2 Unit"},
        {"_id": "U_AMB3", "username": "amb3", "password_hash": hash_password("amb123"), "role": "AMBULANCE", "ref": "A3", "display": "Ambulance A3 Unit"},
        {"_id": "U_AMB4", "username": "amb4", "password_hash": hash_password("amb123"), "role": "AMBULANCE", "ref": "A4", "display": "Ambulance A4 Unit"},
        {"_id": "U_AMB5", "username": "amb5", "password_hash": hash_password("amb123"), "role": "AMBULANCE", "ref": "A5", "display": "Ambulance A5 Unit"},
        {"_id": "U_HOSP1", "username": "hosp1", "password_hash": hash_password("hosp123"), "role": "HOSPITAL", "ref": "H1", "display": "Hospital A (St. Jude)"},
        {"_id": "U_HOSP2", "username": "hosp2", "password_hash": hash_password("hosp123"), "role": "HOSPITAL", "ref": "H2", "display": "Hospital B (Metro Central)"},
        {"_id": "U_HOSP3", "username": "hosp3", "password_hash": hash_password("hosp123"), "role": "HOSPITAL", "ref": "H3", "display": "Hospital C (Community West)"},
    ]
    db_inst.users.insert_many(users)

    # 2. Hospitals (§14: H1: 8 beds/2 ICU/trauma; H2: 30 beds/6 ICU/trauma; H3: 12 beds/no ICU/no trauma)
    hospitals = [
        {
            "_id": "H1",
            "name": "Hospital A (St. Jude)",
            "node": "N5",
            "location": {"type": "Point", "coordinates": NODES["N5"]["coords"]},
            "total_beds": 8,
            "available_beds": 8,
            "icu_total": 2,
            "icu_available": 2,
            "trauma": 1
        },
        {
            "_id": "H2",
            "name": "Hospital B (Metro Central)",
            "node": "N6",
            "location": {"type": "Point", "coordinates": NODES["N6"]["coords"]},
            "total_beds": 30,
            "available_beds": 30,
            "icu_total": 6,
            "icu_available": 6,
            "trauma": 1
        },
        {
            "_id": "H3",
            "name": "Hospital C (Community West)",
            "node": "N7",
            "location": {"type": "Point", "coordinates": NODES["N7"]["coords"]},
            "total_beds": 12,
            "available_beds": 12,
            "icu_total": 0,
            "icu_available": 0,
            "trauma": 0
        }
    ]
    db_inst.hospitals.insert_many(hospitals)

    # 3. Ambulances (§14: 5 ambulances)
    ambulances = [
        {"_id": "A1", "name": "Ambulance A1", "node": "N1", "location": {"type": "Point", "coordinates": NODES["N1"]["coords"]}, "capacity": 4, "status": "available"},
        {"_id": "A2", "name": "Ambulance A2", "node": "N2", "location": {"type": "Point", "coordinates": NODES["N2"]["coords"]}, "capacity": 4, "status": "available"},
        {"_id": "A3", "name": "Ambulance A3", "node": "N3", "location": {"type": "Point", "coordinates": NODES["N3"]["coords"]}, "capacity": 4, "status": "available"},
        {"_id": "A4", "name": "Ambulance A4", "node": "N4", "location": {"type": "Point", "coordinates": NODES["N4"]["coords"]}, "capacity": 4, "status": "available"},
        {"_id": "A5", "name": "Ambulance A5", "node": "N1", "location": {"type": "Point", "coordinates": NODES["N1"]["coords"]}, "capacity": 4, "status": "available"},
    ]
    db_inst.ambulances.insert_many(ambulances)

    # 4. Rescue Teams
    rescue_teams = [
        {"_id": "R1", "name": "Rescue Team Alpha", "node": "N1", "location": {"type": "Point", "coordinates": NODES["N1"]["coords"]}, "status": "active"}
    ]
    db_inst.rescue_teams.insert_many(rescue_teams)

    # 5. Roads
    db_inst.roads.insert_many(DEFAULT_ROADS)

    # 6. Settings
    db_inst.settings.insert_many([
        {"_id": "risk_mult", "value": 1.0},
        {"_id": "inc_seq", "value": 0}
    ])

    # 7. Initial Events (Adaptation Log)
    db_inst.events.insert_one({
        "_id": "EVT_INIT",
        "type": "system",
        "message": "System initialized. Shared backend state online. 3 hospitals, 5 ambulances, 9 roads ready.",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    print("Demo data seeded successfully.")
