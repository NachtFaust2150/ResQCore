import math
from datetime import datetime, timezone
from app.core.routing import find_shortest_path, NODES
from app.core.priority import calculate_priority_score
from app.core.risk_model import risk_predictor

try:
    from ortools.sat.python import cp_model
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False

def run_plan(db) -> dict:
    """
    Main decision engine loop.
    Triggered on any change (report, capacity change, road block, risk change, new incident).
    Performs full re-plan over all open incidents.
    """
    # 1. Fetch current settings & data
    settings = db.settings.find_one({"_id": "risk_mult"})
    risk_mult = float(settings["value"]) if settings and "value" in settings else 1.0

    roads = list(db.roads.find())
    open_incidents = list(db.incidents.find({"status": {"$ne": "closed"}}))
    ambulances = list(db.ambulances.find())
    hospitals = list(db.hospitals.find())
    existing_assignments = {a["ambulance_id"]: a for a in db.assignments.find()}

    if not open_incidents:
        # Reset all ambulance statuses to available if no open incidents
        db.ambulances.update_many({}, {"$set": {"status": "available"}})
        db.assignments.delete_many({})
        return {"status": "success", "message": "No open incidents", "assignments": []}

    # 2. Update priority scores for open incidents
    for inc in open_incidents:
        crit = int(inc.get("critical", 0))
        ser = int(inc.get("serious", 0))
        mod = int(inc.get("moderate", 0))

        # Calculate area risk for incident node
        inc_node = inc.get("area", "N1")
        if inc_node not in NODES:
            inc_node = "N1"
            inc["area"] = "N1"

        node_data = NODES[inc_node]
        node_risk = risk_predictor.predict_risk(
            node_data["dist_river"], node_data["elevation"], node_data["drainage"], node_data["rainfall"]
        )

        # Wait time in minutes
        created_at = inc.get("created_at")
        wait_min = 0.0
        if isinstance(created_at, str):
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                wait_min = (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
            except Exception:
                wait_min = 0.0

        p_score, p_level = calculate_priority_score(crit, ser, mod, area_risk=node_risk, wait_minutes=wait_min)
        inc["priority_score"] = p_score
        inc["priority"] = p_level

        db.incidents.update_one(
            {"_id": inc["_id"]},
            {"$set": {"priority_score": p_score, "priority": p_level, "area": inc_node}}
        )

    # Sort incidents by priority_score descending
    open_incidents.sort(key=lambda x: x["priority_score"], reverse=True)

    # 3. CP-SAT / Greedy Allocation: Ambulance -> Incident
    amb_capacity = 4
    for inc in open_incidents:
        total_v = int(inc.get("critical", 0)) + int(inc.get("serious", 0)) + int(inc.get("moderate", 0))
        inc["required_ambulances"] = max(1, math.ceil(total_v / amb_capacity))

    allocation_map = {} # incident_id -> list of ambulance_ids

    if ORTOOLS_AVAILABLE and len(ambulances) > 0 and len(open_incidents) > 0:
        allocation_map = _solve_cpsat_allocation(ambulances, open_incidents, roads, risk_mult)
    else:
        allocation_map = _solve_greedy_allocation(ambulances, open_incidents, roads, risk_mult)

    # 4. Capacity-aware Hospital Selection
    # Track remaining capacities during selection
    rem_beds = {h["_id"]: int(h.get("available_beds", 0)) for h in hospitals}
    rem_icu = {h["_id"]: int(h.get("icu_available", 0)) for h in hospitals}
    hosp_by_id = {h["_id"]: h for h in hospitals}

    new_assignments = []
    assigned_amb_ids = set()
    events_to_log = []

    for inc in open_incidents:
        inc_id = inc["_id"]
        assigned_ambs = allocation_map.get(inc_id, [])
        if not assigned_ambs:
            continue

        inc_node = inc.get("area", "N1")
        total_v = int(inc.get("critical", 0)) + int(inc.get("serious", 0)) + int(inc.get("moderate", 0))
        crit_v = int(inc.get("critical", 0))

        # Find best feasible hospital
        best_hosp_id = None
        best_hosp_cost = float("inf")
        best_hosp_route = None

        # Filter feasible hospitals
        feasible_hospitals = []
        for h in hospitals:
            h_id = h["_id"]
            beds_avail = rem_beds[h_id]
            icu_avail = rem_icu[h_id]
            trauma_ok = (h.get("trauma", 0) == 1)

            # Feasibility check: beds >= total_v, and if crit > 0 -> trauma_ok and icu >= crit
            if beds_avail >= total_v:
                if crit_v > 0:
                    if trauma_ok and icu_avail >= crit_v:
                        feasible_hospitals.append(h)
                else:
                    feasible_hospitals.append(h)

        # Fallback if no hospital can accommodate all beds/ICU: pick hospital with max beds
        if not feasible_hospitals:
            hospitals_sorted = sorted(hospitals, key=lambda h: (rem_beds[h["_id"]], rem_icu[h["_id"]]), reverse=True)
            feasible_hospitals = [hospitals_sorted[0]] if hospitals_sorted else hospitals

        for h in feasible_hospitals:
            h_node = h.get("node", "N5")
            route = find_shortest_path(inc_node, h_node, roads, risk_mult)
            if route["weighted_cost"] < best_hosp_cost:
                best_hosp_cost = route["weighted_cost"]
                best_hosp_id = h["_id"]
                best_hosp_route = route

        # Deduct beds & ICU for chosen hospital
        if best_hosp_id in rem_beds:
            rem_beds[best_hosp_id] = max(0, rem_beds[best_hosp_id] - total_v)
            if crit_v > 0:
                rem_icu[best_hosp_id] = max(0, rem_icu[best_hosp_id] - crit_v)

        chosen_hosp = hosp_by_id.get(best_hosp_id, hospitals[0])

        # Assign each ambulance allocated to this incident
        for amb_id in assigned_ambs:
            assigned_amb_ids.add(amb_id)
            amb_doc = db.ambulances.find_one({"_id": amb_id})
            amb_node = amb_doc.get("node", "N1") if amb_doc else "N1"

            # Route 1: Ambulance -> Incident
            route_inc = find_shortest_path(amb_node, inc_node, roads, risk_mult)
            # Route 2: Incident -> Hospital
            route_hosp = best_hosp_route if best_hosp_route else find_shortest_path(inc_node, chosen_hosp.get("node", "N5"), roads, risk_mult)

            # Check for reallocation / destination change
            prev_asgn = existing_assignments.get(amb_id)
            if prev_asgn and prev_asgn.get("hospital_id") != best_hosp_id:
                prev_h_name = hosp_by_id.get(prev_asgn.get("hospital_id"), {}).get("name", prev_asgn.get("hospital_id"))
                reason = f"Capacity shift / Optimization recalculation for incident {inc_id}"
                if hosp_by_id.get(prev_asgn.get("hospital_id"), {}).get("available_beds", 0) <= 0:
                    reason = f"Previous hospital ({prev_h_name}) capacity exhausted (0 beds)"
                events_to_log.append({
                    "type": "reallocation",
                    "message": f"Ambulance {amb_id} reallocated from {prev_h_name} to {chosen_hosp['name']}. Reason: {reason}",
                    "created_at": datetime.now(timezone.utc).isoformat()
                })

            asgn_doc = {
                "_id": f"ASGN_{amb_id}_{inc_id}",
                "incident_id": inc_id,
                "ambulance_id": amb_id,
                "hospital_id": best_hosp_id,
                "hospital_name": chosen_hosp.get("name"),
                "route_to_incident": route_inc["coords"],
                "route_to_hospital": route_hosp["coords"],
                "incident_node": inc_node,
                "hospital_node": chosen_hosp.get("node"),
                "travel_time_to_inc": route_inc["travel_time"],
                "travel_time_to_hosp": route_hosp["travel_time"],
                "status": "assigned",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            new_assignments.append(asgn_doc)

    # 5. Database State Updates
    # Update assignments collection
    db.assignments.delete_many({})
    if new_assignments:
        db.assignments.insert_many(new_assignments)

    # Update ambulance statuses
    for a in ambulances:
        a_id = a["_id"]
        if a_id in assigned_amb_ids:
            db.ambulances.update_one({"_id": a_id}, {"$set": {"status": "assigned"}})
        else:
            db.ambulances.update_one({"_id": a_id}, {"$set": {"status": "available"}})

    # Update incident statuses
    for inc in open_incidents:
        inc_id = inc["_id"]
        if inc_id in allocation_map and len(allocation_map[inc_id]) > 0:
            db.incidents.update_one({"_id": inc_id}, {"$set": {"status": "allocated"}})
        else:
            db.incidents.update_one({"_id": inc_id}, {"$set": {"status": "pending"}})

    # Log events
    if events_to_log:
        db.events.insert_many(events_to_log)

    return {
        "status": "success",
        "assignments_count": len(new_assignments),
        "open_incidents_count": len(open_incidents),
        "reallocations": len(events_to_log)
    }

def _solve_cpsat_allocation(ambulances: list[dict], incidents: list[dict], roads: list[dict], risk_mult: float) -> dict[str, list[str]]:
    """
    CP-SAT ambulance-to-incident allocation solver.
    """
    model = cp_model.CpModel()
    x = {} # (a_id, inc_id) -> BoolVar
    u = {} # inc_id -> IntVar (slack)

    amb_ids = [a["_id"] for a in ambulances]
    inc_ids = [i["_id"] for i in incidents]

    # Precalculate costs
    cost_map = {}
    for a in ambulances:
        a_id = a["_id"]
        a_node = a.get("node", "N1")
        for i in incidents:
            i_id = i["_id"]
            i_node = i.get("area", "N1")
            route = find_shortest_path(a_node, i_node, roads, risk_mult)
            # Cost = travel_time * (1 + 0.8 * route_risk)
            cost_val = route["travel_time"] * (1.0 + 0.8 * route["avg_risk"])
            cost_map[(a_id, i_id)] = int(cost_val * 100) # Integer for CP-SAT

    # Decision variables
    for a_id in amb_ids:
        for i_id in inc_ids:
            x[(a_id, i_id)] = model.NewBoolVar(f"x_{a_id}_{i_id}")

    for i in incidents:
        i_id = i["_id"]
        req = i["required_ambulances"]
        u[i_id] = model.NewIntVar(0, req, f"u_{i_id}")

    # Constraints
    # 1. Each ambulance assigned to at most 1 incident
    for a_id in amb_ids:
        model.Add(sum(x[(a_id, i_id)] for i_id in inc_ids) <= 1)

    # 2. Demand fulfillment constraint per incident: sum_a x[a][i] + u[i] == required_i
    for i in incidents:
        i_id = i["_id"]
        req = i["required_ambulances"]
        model.Add(sum(x[(a_id, i_id)] for a_id in amb_ids) + u[i_id] == req)

    # Objective: Minimize cost + slack penalty
    # Penalty constant
    BIG_PENALTY = 100000
    objective_terms = []
    for a_id in amb_ids:
        for i_id in inc_ids:
            objective_terms.append(x[(a_id, i_id)] * cost_map[(a_id, i_id)])

    for i in incidents:
        i_id = i["_id"]
        p_score = i["priority_score"]
        slack_weight = int(BIG_PENALTY * (1.0 + p_score))
        objective_terms.append(u[i_id] * slack_weight)

    model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2.0
    sol_status = solver.Solve(model)

    allocation_result = {i_id: [] for i_id in inc_ids}
    if sol_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for a_id in amb_ids:
            for i_id in inc_ids:
                if solver.Value(x[(a_id, i_id)]) == 1:
                    allocation_result[i_id].append(a_id)
        return allocation_result

    # Fallback to greedy if CP-SAT failed
    return _solve_greedy_allocation(ambulances, incidents, roads, risk_mult)

def _solve_greedy_allocation(ambulances: list[dict], incidents: list[dict], roads: list[dict], risk_mult: float) -> dict[str, list[str]]:
    """
    Greedy fallback ambulance allocation.
    """
    unassigned_ambs = {a["_id"]: a for a in ambulances}
    allocation_result = {i["_id"]: [] for i in incidents}

    # Sort incidents by priority_score descending
    sorted_incidents = sorted(incidents, key=lambda x: x["priority_score"], reverse=True)

    for i in sorted_incidents:
        i_id = i["_id"]
        i_node = i.get("area", "N1")
        req = i["required_ambulances"]

        # Rank remaining unassigned ambulances by cost to this incident
        candidates = []
        for a_id, a in unassigned_ambs.items():
            a_node = a.get("node", "N1")
            route = find_shortest_path(a_node, i_node, roads, risk_mult)
            cost_val = route["travel_time"] * (1.0 + 0.8 * route["avg_risk"])
            candidates.append((cost_val, a_id))

        candidates.sort(key=lambda x: x[0])

        # Pick top `req` ambulances
        for cost_val, a_id in candidates[:req]:
            allocation_result[i_id].append(a_id)
            del unassigned_ambs[a_id]

    return allocation_result
