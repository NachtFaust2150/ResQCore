// Hospital Capacity Controller

function renderHospitalView(state) {
    const hospRef = currentUser ? currentUser.ref : "H1";
    const hospDoc = (state.hospitals || []).find(h => h._id === hospRef);

    if (!hospDoc) return;

    // 1. Update Metrics Cards
    document.getElementById("hosp-beds-val").textContent = `${hospDoc.available_beds} / ${hospDoc.total_beds}`;
    document.getElementById("hosp-icu-val").textContent = `${hospDoc.icu_available} / ${hospDoc.icu_total}`;
    document.getElementById("hosp-trauma-val").textContent = hospDoc.trauma === 1 ? "Trauma-capable: Yes" : "Trauma-capable: No";

    // Set max/min limits on form inputs
    const formBeds = document.getElementById("hosp-form-beds");
    const formIcu = document.getElementById("hosp-form-icu");
    if (formBeds) {
        formBeds.max = hospDoc.total_beds;
        if (document.activeElement !== formBeds) formBeds.value = hospDoc.available_beds;
    }
    if (formIcu) {
        formIcu.max = hospDoc.icu_total;
        if (document.activeElement !== formIcu) formIcu.value = hospDoc.icu_available;
    }

    // 2. Render Incoming Ambulances Grouped by Incident
    const incomingAssignments = (state.assignments || []).filter(a => a.hospital_id === hospRef);
    const container = document.getElementById("hospital-incoming-container");

    if (!container) return;

    if (incomingAssignments.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.9rem; padding: 1rem 0;">No inbound ambulances currently routed to this hospital.</div>';
        return;
    }

    const incidentsMap = {};
    (state.incidents || []).forEach(i => incidentsMap[i._id] = i);

    // Group assignments by incident ID
    const grouped = {};
    incomingAssignments.forEach(asgn => {
        grouped[asgn.incident_id] = grouped[asgn.incident_id] || [];
        grouped[asgn.incident_id].push(asgn);
    });

    container.innerHTML = Object.keys(grouped).map(incId => {
        const asgnList = grouped[incId];
        const inc = incidentsMap[incId];
        const victimMixText = inc
            ? `<span style="color: var(--accent-red); font-weight:700;">${inc.critical} Critical</span>, <span style="color: var(--accent-orange); font-weight:700;">${inc.serious} Serious</span>, <span style="color: var(--accent-green); font-weight:700;">${inc.moderate} Moderate</span>`
            : "Victims En Route";
        const nodeText = inc ? `Node ${inc.area}` : `Node ${asgnList[0].incident_node}`;

        const ambRows = asgnList.map(a => {
            const totalEta = (a.travel_time_to_inc + a.travel_time_to_hosp).toFixed(1);
            return `
                <tr>
                    <td><strong>Ambulance ${a.ambulance_id}</strong></td>
                    <td><strong style="color: var(--accent-purple);">${totalEta} min</strong></td>
                    <td><span class="badge badge-enroute">EN ROUTE</span></td>
                </tr>
            `;
        }).join("");

        return `
            <div style="background: #0b0f19; border: 1px solid var(--border-color); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 0.5rem; margin-bottom: 0.75rem;">
                    <div>
                        <strong style="font-size: 1rem;">Incident ${incId}</strong>
                        <span style="font-size: 0.8rem; color: var(--text-muted); margin-left: 0.5rem;">(${nodeText})</span>
                    </div>
                    <div style="font-size: 0.85rem;">Total Incident Victims: ${victimMixText}</div>
                </div>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>Assigned Unit</th>
                                <th>Route Total ETA</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${ambRows}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }).join("");
}

async function submitHospitalCapacity(e) {
    e.preventDefault();
    const errDiv = document.getElementById("hosp-capacity-error");
    if (errDiv) errDiv.style.display = "none";

    const hospRef = currentUser ? currentUser.ref : "H1";
    const hospDoc = (appState?.hospitals || []).find(h => h._id === hospRef);

    const available_beds = parseInt(document.getElementById("hosp-form-beds").value, 10);
    const icu_available = parseInt(document.getElementById("hosp-form-icu").value, 10);

    if (hospDoc) {
        if (available_beds < 0 || available_beds > hospDoc.total_beds) {
            if (errDiv) {
                errDiv.textContent = `Available beds (${available_beds}) must be between 0 and total beds (${hospDoc.total_beds})`;
                errDiv.style.display = "block";
            }
            return;
        }
        if (icu_available < 0 || icu_available > hospDoc.icu_total) {
            if (errDiv) {
                errDiv.textContent = `Available ICU beds (${icu_available}) must be between 0 and total ICU beds (${hospDoc.icu_total})`;
                errDiv.style.display = "block";
            }
            return;
        }
    }

    try {
        await apiRequest("/api/hospital/capacity", {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ available_beds, icu_available })
        });
        showToast("Hospital capacity updated! Re-plan triggered.");
        await fetchState();
    } catch (err) {
        if (errDiv) {
            errDiv.textContent = err.message;
            errDiv.style.display = "block";
        }
    }
}
