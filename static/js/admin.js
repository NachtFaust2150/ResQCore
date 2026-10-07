// Admin Dashboard Controller

function renderAdminView(state) {
    // 1. Render Metrics
    const totalAmbs = (state.ambulances || []).length;
    const assignedAmbs = (state.ambulances || []).filter(a => a.status !== "available").length;
    document.getElementById("m-amb-status").textContent = `${totalAmbs - assignedAmbs} / ${totalAmbs} Free`;

    let totalBeds = 0, availBeds = 0, totalIcu = 0, availIcu = 0;
    (state.hospitals || []).forEach(h => {
        totalBeds += h.total_beds || 0;
        availBeds += h.available_beds || 0;
        totalIcu += h.icu_total || 0;
        availIcu += h.icu_available || 0;
    });
    document.getElementById("m-beds-status").textContent = `${availBeds} / ${totalBeds}`;
    document.getElementById("m-icu-status").textContent = `ICU: ${availIcu} / ${totalIcu}`;

    const riskMult = state.settings ? (state.settings.risk_mult || 1.0) : 1.0;
    document.getElementById("m-risk-mult").textContent = `${riskMult}x`;

    const openIncidents = (state.incidents || []).filter(i => i.status !== "closed");
    document.getElementById("m-incidents-count").textContent = openIncidents.length;

    // 2. Render Active Incidents Table
    const incBody = document.getElementById("admin-incidents-body");
    if (openIncidents.length === 0) {
        incBody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No active incidents in system.</td></tr>';
    } else {
        const asgnByInc = {};
        (state.assignments || []).forEach(a => {
            asgnByInc[a.incident_id] = asgnByInc[a.incident_id] || [];
            asgnByInc[a.incident_id].push(a);
        });

        incBody.innerHTML = openIncidents.map(inc => {
            const assignedList = asgnByInc[inc._id] || [];
            const ambNames = assignedList.map(a => a.ambulance_id).join(", ") || "None";
            const targetHosp = assignedList.length > 0 ? (assignedList[0].hospital_name || assignedList[0].hospital_id) : "Unassigned";
            const pBadgeClass = `badge-${(inc.priority || "Low").toLowerCase()}`;

            return `
                <tr>
                    <td><strong>${inc._id}</strong></td>
                    <td>Node ${inc.area || 'N1'}</td>
                    <td><span style="color: var(--accent-red); font-weight: 700;">${inc.critical}</span> / <span style="color: var(--accent-orange); font-weight: 700;">${inc.serious}</span> / <span style="color: var(--accent-green); font-weight: 700;">${inc.moderate}</span></td>
                    <td><span class="badge ${pBadgeClass}">${inc.priority_score || 0} (${inc.priority || 'Low'})</span></td>
                    <td>${ambNames}</td>
                    <td><strong style="color: var(--accent-purple);">${targetHosp}</strong></td>
                    <td><span class="badge badge-${inc.status === 'allocated' ? 'allocated' : 'assigned'}">${inc.status.toUpperCase()}</span></td>
                </tr>
            `;
        }).join("");
    }

    // 3. Render Ambulance Assignments Table
    const ambBody = document.getElementById("admin-ambulances-body");
    const assignmentsMap = {};
    (state.assignments || []).forEach(a => {
        assignmentsMap[a.ambulance_id] = a;
    });

    ambBody.innerHTML = (state.ambulances || []).map(amb => {
        const asgn = assignmentsMap[amb._id];
        const statusBadge = amb.status === "available" ? "badge-available" : "badge-assigned";
        const incId = asgn ? asgn.incident_id : "—";
        const hospName = asgn ? (asgn.hospital_name || asgn.hospital_id) : "—";
        const etaText = asgn ? `${asgn.travel_time_to_inc}m / ${asgn.travel_time_to_hosp}m` : "—";

        return `
            <tr>
                <td><strong>${amb.name} (${amb._id})</strong></td>
                <td>Node ${amb.node}</td>
                <td><span class="badge ${statusBadge}">${amb.status.toUpperCase()}</span></td>
                <td>${incId}</td>
                <td><strong style="color: var(--accent-purple);">${hospName}</strong></td>
                <td>${etaText}</td>
            </tr>
        `;
    }).join("");
}

/* Simulation Trigger Handlers */

async function triggerSimHospitalFull(hospitalId = 'H1') {
    try {
        await apiRequest("/api/sim/hospital_full", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hospital_id: hospitalId })
        });
        showToast("Simulation: Hospital A set to 0 beds.");
        await fetchState();
    } catch (err) {
        showToast(`Simulation Error: ${err.message}`);
    }
}

async function triggerSimRoadBlock(roadId = 'R3') {
    try {
        await apiRequest("/api/sim/road_block", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ road_id: roadId, blocked: 1 })
        });
        showToast("Simulation: Road R3 marked blocked.");
        await fetchState();
    } catch (err) {
        showToast(`Simulation Error: ${err.message}`);
    }
}

async function triggerSimRiskIncrease(multiplier = 2.0) {
    try {
        await apiRequest("/api/sim/risk_increase", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ multiplier: multiplier })
        });
        showToast("Simulation: Risk multiplier raised to 2.0x.");
        await fetchState();
    } catch (err) {
        showToast(`Simulation Error: ${err.message}`);
    }
}

async function triggerSimNewIncident() {
    try {
        const res = await apiRequest("/api/sim/new_incident", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                area: "N3",
                critical: 1,
                serious: 2,
                moderate: 1,
                notes: "Simulated Secondary Incident at Junction West N3"
            })
        });
        showToast(`Simulation: Secondary incident ${res.incident_id} created at Node N3.`);
        await fetchState();
    } catch (err) {
        showToast(`Simulation Error: ${err.message}`);
    }
}

async function triggerSimReset() {
    try {
        await apiRequest("/api/sim/reset", { method: "POST" });
        showToast("System reset to initial demo state.");
        await fetchState();
    } catch (err) {
        showToast(`Reset Error: ${err.message}`);
    }
}
