# ResQCore — AI Disaster Response & Dynamic Resource Allocation

ResQCore is a working prototype of an AI-assisted disaster response and dynamic resource allocation system built with Python, FastAPI, MongoDB, Google OR-Tools, and Leaflet.

---

## 1. Objective & Core Loop

ResQCore monitors disaster incidents reported by field rescue teams, determines optimal ambulance dispatch and hospital destinations, propagates decisions to every role's dashboard from one shared backend state, and **automatically re-plans** whenever conditions change (hospital full, road blocked, risk increase, or new emergency).

Core Loop: **Report → Verify → Assess → Optimize → Dispatch → Monitor → Re-plan.**

---

## 2. Roles and Permissions (RBAC)

Enforced server-side via PyJWT tokens on every endpoint:

| Role | Permissions | Dashboard Route |
|---|---|---|
| **ADMIN** | Simulation controls, state oversight | `/admin` |
| **RESCUE** | Incident field reports (create/update) | `/rescue` |
| **AMBULANCE** | View assigned mission, status & route | `/ambulance` |
| **HOSPITAL** | Live capacity updates (Beds, ICU) | `/hospital` |

> Note: Cross-role unauthorized writes (e.g. RESCUE token calling HOSPITAL capacity endpoint) return HTTP 403 Forbidden.

---

## 3. Tech Stack

- **Backend**: Python 3.11+ with **FastAPI**
- **Database**: **MongoDB** (single store, collections: `users`, `hospitals`, `ambulances`, `rescue_teams`, `roads`, `incidents`, `assignments`, `events`, `settings`). 2dsphere index on location fields. Automatic in-memory fallback if local MongoDB service is unavailable.
- **Auth**: **JWT** (PyJWT) with PBKDF2 password hashing.
- **AI — Risk Model**: **scikit-learn RandomForestRegressor** trained at startup on synthetic location features (distance to river, elevation, drainage, rainfall). Exposes feature importances on UI.
- **AI — Priority**: Transparent weighted scoring:  
  `score = critical*3 + serious*2 + moderate*1 + area_risk*2 + min(wait_min, 30)*0.05`
- **Optimizer**: **Google OR-Tools CP-SAT** for ambulance→incident allocation with greedy fallback.
- **Routing**: **Simplified 7-node / 9-edge road graph + Dijkstra algorithm** (Edge weight = `travel_time * (1 + 0.8 * edge_risk * risk_multiplier)`). Blocked roads are removed from the graph.
- **Map & UI**: **Leaflet + OpenStreetMap** raster tiles, Vanilla HTML/CSS/JS, 2.5s polling loop for real-time state synchronization across dashboards.

---

## 4. Quick Run Instructions

### Prerequisites
Python 3.11+ installed.

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Run Application
```bash
uvicorn app.main:app --reload
```
Open your browser at **`http://localhost:8000`**

### Step 3: Run Automated Test Suite
To verify the end-to-end 7-step demo scenario and RBAC enforcement:
```bash
python test_demo.py
```

---

## 5. Demo Credentials

| Role | Username | Password | Default Assignment / Reference |
|---|---|---|---|
| Admin | `admin` | `admin123` | System Coordinator |
| Rescue | `rescue1` | `rescue123` | Rescue Team Alpha |
| Ambulance 1 | `amb1` | `amb123` | Ambulance A1 Unit |
| Hospital A | `hosp1` | `hosp123` | Hospital A (St. Jude) |
| Hospital B | `hosp2` | `hosp123` | Hospital B (Metro Central) |
| Hospital C | `hosp3` | `hosp123` | Hospital C (Community West) |

---

## 6. Demo Scenario Flow (§14)

1. **Rescue Report**: Log in as `rescue1` and submit a field report (2 Critical, 3 Serious, 3 Moderate). OR-Tools allocates 2 ambulances (A4, A1) and selects Hospital A.
2. **Ambulance View**: Log in as `amb1` to view assignment, destination hospital, and Leaflet route polyline.
3. **Hospital View**: Log in as `hosp1` to view incoming ambulances and inbound victim count.
4. **Hospital Full Simulation**: Log in as `admin`, click **"Hosp A Full"**. System auto-reallocates ambulances to Hospital B and logs event.
5. **Road Block Simulation**: Click **"Road R3 Blocked"**. Dijkstra recalculates route bypassing blocked edge R3.
6. **Risk Increase Simulation**: Click **"Risk Increase"**. Re-plans routing penalties with 2.0x risk multiplier.
7. **New Emergency Simulation**: Click **"New Emergency"**. Creates secondary incident at Node N3 and re-plans ambulances across both incidents.

---

## 7. Future Scope (Not Implemented in Prototype)

- PostgreSQL/PostGIS for persistent geospatial data
- Redis for live state caching
- SQLite on edge devices & cloud/edge gateway for internet outages
- OSRM routing with real OpenStreetMap street geometries
- Live weather & river sensor API integration
- Management of shelters, volunteers, and medical supplies

---

## 8. Honesty Notes (§17)

- **Risk Model**: The RandomForest model is trained on **synthetic** data at application startup; no real-world prediction accuracy is claimed.
- **Routing**: Routing uses a **simplified 7-node / 9-edge demo road graph**, not real OSRM street networks.
- **Database**: MongoDB (with in-memory mongomock fallback) is the single store; PostGIS, Redis, and edge nodes are proposed for future production scope only.
- **JWT Secret**: Uses a default secret key for prototype demonstration; replace with secure environment secret for real deployment.
