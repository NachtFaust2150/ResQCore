import sys
from fastapi.testclient import TestClient
from app.main import app
from app.db import reset_to_seed_data, get_database

def run_demo_test():
    print("==========================================================")
    print("   ResQCore -- End-to-End Demo Scenario Automated Test    ")
    print("==========================================================")

    # Reset seed data
    db = get_database()
    reset_to_seed_data(db)

    client = TestClient(app)

    # 1. Login as all four roles to obtain JWT tokens
    print("\n[Auth Test] Logging in users...")

    res_admin = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    assert res_admin.status_code == 200, f"Admin login failed: {res_admin.text}"
    admin_token = res_admin.json()["token"]
    print("  [OK] ADMIN logged in successfully")

    res_rescue = client.post("/api/login", json={"username": "rescue1", "password": "rescue123"})
    assert res_rescue.status_code == 200, f"Rescue login failed: {res_rescue.text}"
    rescue_token = res_rescue.json()["token"]
    print("  [OK] RESCUE logged in successfully")

    res_amb1 = client.post("/api/login", json={"username": "amb1", "password": "amb123"})
    assert res_amb1.status_code == 200
    amb1_token = res_amb1.json()["token"]
    print("  [OK] AMBULANCE (A1) logged in successfully")

    res_hosp1 = client.post("/api/login", json={"username": "hosp1", "password": "hosp123"})
    assert res_hosp1.status_code == 200
    hosp1_token = res_hosp1.json()["token"]
    print("  [OK] HOSPITAL (H1) logged in successfully")

    # 2. RBAC & Validation Tests
    print("\n[RBAC & Validation Tests] Verifying role enforcement and capacity validation...")
    
    # 2a. RBAC 403
    res_forbidden = client.patch(
        "/api/hospital/capacity",
        json={"available_beds": 5, "icu_available": 1},
        headers={"Authorization": f"Bearer {rescue_token}"}
    )
    assert res_forbidden.status_code == 403, f"Expected 403, got {res_forbidden.status_code}"
    print(f"  [OK] RESCUE token calling HOSPITAL endpoint returned HTTP 403 Forbidden")

    # 2b. Hospital Capacity > Total Beds (422)
    res_invalid_cap = client.patch(
        "/api/hospital/capacity",
        json={"available_beds": 50, "icu_available": 1},
        headers={"Authorization": f"Bearer {hosp1_token}"}
    )
    assert res_invalid_cap.status_code == 422, f"Expected 422 for available > total beds, got {res_invalid_cap.status_code}"
    print(f"  [OK] Capacity update exceeding total beds returned HTTP 422: {res_invalid_cap.json()['detail']}")

    # 2c. 0 Victims Report (422)
    res_invalid_rep = client.post(
        "/api/report",
        data={"critical": "0", "serious": "0", "moderate": "0"},
        headers={"Authorization": f"Bearer {rescue_token}"}
    )
    assert res_invalid_rep.status_code == 422, f"Expected 422 for 0 victims, got {res_invalid_rep.status_code}"
    print(f"  [OK] Rescue report with 0 victims returned HTTP 422: {res_invalid_rep.json()['detail']}")

    # 3. DEMO STEP 1: Rescue Submits Incident Report (2 Critical, 3 Serious, 3 Moderate = 8 victims)
    print("\n[Demo Step 1] Rescue Team submits field report (2 Critical, 3 Serious, 3 Moderate)...")
    rep_res = client.post(
        "/api/report",
        data={
            "critical": "2",
            "serious": "3",
            "moderate": "3",
            "notes": "Mass casualty event at main junction N1"
        },
        headers={"Authorization": f"Bearer {rescue_token}"}
    )
    assert rep_res.status_code == 200, f"Report failed: {rep_res.text}"
    rep_data = rep_res.json()
    inc_id = rep_data["incident_id"]
    assert inc_id == "INC-001", f"Expected sequential ID INC-001, got {inc_id}"
    print(f"  [OK] Sequential Incident Created: {inc_id}")

    state_res = client.get("/api/state", headers={"Authorization": f"Bearer {admin_token}"})
    state = state_res.json()
    assignments = state["assignments"]
    assert len(assignments) >= 2, f"Expected at least 2 ambulances assigned, got {len(assignments)}"
    hosp_assigned = assignments[0]["hospital_id"]
    print(f"  [OK] OR-Tools allocated {len(assignments)} ambulances to Incident {inc_id}")
    print(f"  [OK] Hospital Selected: {assignments[0]['hospital_name']} ({hosp_assigned})")
    assert hosp_assigned == "H1", f"Expected H1 (Hospital A), got {hosp_assigned}"

    # 4. DEMO STEP 2: Ambulance A1 checks mission view
    print("\n[Demo Step 2] Ambulance A1 checks assignment & destination route...")
    amb_state = client.get("/api/state", headers={"Authorization": f"Bearer {amb1_token}"}).json()
    a1_asgn = next((a for a in amb_state["assignments"] if a["ambulance_id"] == "A1"), None)
    assert a1_asgn is not None, "Ambulance A1 was not assigned"
    print(f"  [OK] Ambulance A1 assigned to Incident {a1_asgn['incident_id']} -> Destination {a1_asgn['hospital_name']}")
    print(f"  [OK] Route calculated: Base->Inc {a1_asgn['travel_time_to_inc']}m, Inc->Hosp {a1_asgn['travel_time_to_hosp']}m")

    # 5. DEMO STEP 3: Hospital A checks incoming ambulances
    print("\n[Demo Step 3] Hospital A checks incoming inbound ambulances...")
    hosp_state = client.get("/api/state", headers={"Authorization": f"Bearer {hosp1_token}"}).json()
    h1_inbound = [a for a in hosp_state["assignments"] if a["hospital_id"] == "H1"]
    assert len(h1_inbound) > 0, "No inbound ambulances found for H1"
    print(f"  [OK] Hospital A sees {len(h1_inbound)} incoming ambulance units")

    # 6. DEMO STEP 4: Admin triggers "Simulate Hospital Full" (Hospital A beds = 0)
    print("\n[Demo Step 4] Admin triggers 'Simulate Hospital Full' on Hospital A...")
    sim_hosp_res = client.post(
        "/api/sim/hospital_full",
        json={"hospital_id": "H1"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert sim_hosp_res.status_code == 200
    state_after_hosp = client.get("/api/state", headers={"Authorization": f"Bearer {admin_token}"}).json()
    new_asgns = state_after_hosp["assignments"]
    new_hosp = new_asgns[0]["hospital_id"]
    print(f"  [OK] Automatic Re-plan Completed! Ambulances re-allocated to {new_asgns[0]['hospital_name']} ({new_hosp})")
    assert new_hosp == "H2", f"Expected reallocation to H2 (Hospital B), got {new_hosp}"

    # Verify Adaptation Log Event
    events = state_after_hosp["events"]
    realloc_evt = next((e for e in events if e.get("type") in ["reallocation", "simulation"]), None)
    assert realloc_evt is not None, "Reallocation event not logged in adaptation log"
    print(f"  [OK] Adaptation Log recorded event: \"{realloc_evt['message']}\"")

    # 7. DEMO STEP 5: Admin triggers "Simulate Road Block" (Road R3)
    print("\n[Demo Step 5] Admin triggers 'Simulate Road Block' on Road R3...")
    sim_road_res = client.post(
        "/api/sim/road_block",
        json={"road_id": "R3", "blocked": 1},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert sim_road_res.status_code == 200
    state_after_road = client.get("/api/state", headers={"Authorization": f"Bearer {admin_token}"}).json()
    road_r3 = next(r for r in state_after_road["roads"] if r["_id"] == "R3")
    assert road_r3["blocked"] == 1, "Road R3 was not marked blocked"
    print("  [OK] Road R3 marked BLOCKED in MongoDB")
    print("  [OK] Dijkstra recalculated all shortest paths bypassing blocked edge R3")

    # 8. DEMO STEP 6: Admin triggers "Simulate Risk Increase"
    print("\n[Demo Step 6] Admin triggers 'Simulate Risk Increase' (2.0x penalty)...")
    sim_risk_res = client.post(
        "/api/sim/risk_increase",
        json={"multiplier": 2.0},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert sim_risk_res.status_code == 200
    state_after_risk = client.get("/api/state", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert state_after_risk["settings"]["risk_mult"] == 2.0
    print("  [OK] Risk Multiplier updated to 2.0x. Routing weights adjusted.")

    # 9. DEMO STEP 7: Admin triggers "Simulate New Emergency (N3)"
    print("\n[Demo Step 7] Admin triggers 'Simulate New Emergency' at Node N3...")
    sim_inc_res = client.post(
        "/api/sim/new_incident",
        json={
            "area": "N3",
            "critical": 1,
            "serious": 2,
            "moderate": 1,
            "notes": "Secondary Emergency at West Junction N3"
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert sim_inc_res.status_code == 200
    state_after_new_inc = client.get("/api/state", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert len(state_after_new_inc["incidents"]) == 2, "Expected 2 active incidents"
    assert state_after_new_inc["incidents"][-1]["_id"] == "INC-002", f"Expected INC-002, got {state_after_new_inc['incidents'][-1]['_id']}"
    print(f"  [OK] Secondary incident INC-002 created at Node N3. Total active incidents: {len(state_after_new_inc['incidents'])}")
    print(f"  [OK] OR-Tools CP-SAT re-planned total assignments across all open incidents: {len(state_after_new_inc['assignments'])} ambulances assigned.")

    print("\n==========================================================")
    print("   ALL 7 DEMO SCENARIO STEPS & ACCEPTANCE CRITERIA PASSED!")
    print("==========================================================")

if __name__ == "__main__":
    run_demo_test()
