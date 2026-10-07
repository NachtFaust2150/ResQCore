// Rescue Dashboard Controller

function updateFileName(input) {
    const textSpan = document.getElementById("photo-label-text");
    if (input.files && input.files.length > 0) {
        textSpan.textContent = `File: ${input.files[0].name}`;
    } else {
        textSpan.textContent = "Upload photo";
    }
}

async function submitFieldReport(e) {
    e.preventDefault();

    const errDiv = document.getElementById("rescue-form-error");
    if (errDiv) errDiv.style.display = "none";

    const critical = parseInt(document.getElementById("rep-critical").value, 10) || 0;
    const serious = parseInt(document.getElementById("rep-serious").value, 10) || 0;
    const moderate = parseInt(document.getElementById("rep-moderate").value, 10) || 0;
    const notes = document.getElementById("rep-notes").value;
    const photoInput = document.getElementById("rep-photo");

    if ((critical + serious + moderate) < 1) {
        if (errDiv) {
            errDiv.textContent = "At least 1 victim required (Critical, Serious, or Moderate)";
            errDiv.style.display = "block";
        }
        return;
    }

    // Capture location via Geolocation API at submit time (non-blocking)
    let capturedLat = null;
    let capturedLng = null;

    if ("geolocation" in navigator) {
        try {
            const pos = await new Promise((resolve, reject) => {
                navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 3000 });
            });
            capturedLat = pos.coords.latitude;
            capturedLng = pos.coords.longitude;
        } catch (geoErr) {
            console.warn("Browser GPS unavailable or denied. Using default demo point.");
            capturedLat = 12.9650;
            capturedLng = 77.5850;
        }
    } else {
        capturedLat = 12.9650;
        capturedLng = 77.5850;
    }

    const formData = new FormData();
    formData.append("critical", critical);
    formData.append("serious", serious);
    formData.append("moderate", moderate);
    formData.append("notes", notes);
    if (capturedLat !== null) formData.append("lat", capturedLat);
    if (capturedLng !== null) formData.append("lng", capturedLng);

    if (photoInput && photoInput.files.length > 0) {
        formData.append("photo", photoInput.files[0]);
    }

    try {
        const res = await fetch("/api/report", {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${currentToken}`
            },
            body: formData
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || "Failed to submit field report");
        }

        const ambList = (data.assigned_ambulances || []).join(", ") || "None yet";
        showToast(`Incident ${data.incident_id} created. Assigned: ${ambList}`);

        document.getElementById("field-report-form").reset();
        updateFileName(document.getElementById("rep-photo"));
        await fetchState();
    } catch (err) {
        if (errDiv) {
            errDiv.textContent = err.message;
            errDiv.style.display = "block";
        }
    }
}

function renderRescueView(state) {
    const body = document.getElementById("rescue-reports-body");
    if (!body) return;

    const incidents = state.incidents || [];
    if (incidents.length === 0) {
        body.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No field reports created yet.</td></tr>';
        return;
    }

    body.innerHTML = incidents.map(inc => {
        const pBadgeClass = `badge-${(inc.priority || "Low").toLowerCase()}`;
        const timeStr = formatTimestamp(inc.created_at);
        return `
            <tr>
                <td><strong>${inc._id}</strong></td>
                <td>Node ${inc.area}</td>
                <td><span style="color: var(--accent-red); font-weight: 700;">${inc.critical}</span> / <span style="color: var(--accent-orange); font-weight: 700;">${inc.serious}</span> / <span style="color: var(--accent-green); font-weight: 700;">${inc.moderate}</span></td>
                <td><span class="badge ${pBadgeClass}">${inc.priority_score} (${inc.priority})</span></td>
                <td><span class="badge badge-assigned">${inc.status.toUpperCase()}</span></td>
                <td>${timeStr}</td>
            </tr>
        `;
    }).join("");
}
