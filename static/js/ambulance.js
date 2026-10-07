// Ambulance Unit Controller

function renderAmbulanceView(state) {
    const ambRef = currentUser ? currentUser.ref : "A1";
    const statusBadge = document.getElementById("amb-unit-status");
    const noMissionAlert = document.getElementById("amb-no-mission");
    const missionCard = document.getElementById("amb-mission-card");

    const ambDoc = (state.ambulances || []).find(a => a._id === ambRef);
    const asgnDoc = (state.assignments || []).find(a => a.ambulance_id === ambRef);

    if (!ambDoc) return;

    if (!asgnDoc || ambDoc.status === "available") {
        statusBadge.textContent = "AVAILABLE";
        statusBadge.className = "badge badge-available";
        noMissionAlert.style.display = "block";
        missionCard.style.display = "none";
    } else {
        statusBadge.textContent = "ASSIGNED / EN ROUTE";
        statusBadge.className = "badge badge-enroute";
        noMissionAlert.style.display = "none";
        missionCard.style.display = "block";

        const incDoc = (state.incidents || []).find(i => i._id === asgnDoc.incident_id);

        document.getElementById("amb-inc-id").textContent = `${asgnDoc.incident_id} (Node ${asgnDoc.incident_node})`;
        if (incDoc) {
            document.getElementById("amb-inc-victims").textContent = `${incDoc.critical} Critical, ${incDoc.serious} Serious, ${incDoc.moderate} Moderate`;
        } else {
            document.getElementById("amb-inc-victims").textContent = "Victims En Route";
        }

        document.getElementById("amb-hosp-name").textContent = asgnDoc.hospital_name || asgnDoc.hospital_id;
        document.getElementById("amb-hosp-node").textContent = `Destination: Node ${asgnDoc.hospital_node}`;

        document.getElementById("amb-eta-inc").textContent = `${asgnDoc.travel_time_to_inc} min`;
        document.getElementById("amb-eta-hosp").textContent = `${asgnDoc.travel_time_to_hosp} min`;
    }
}
