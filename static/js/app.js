// ResQCore Shared Application Logic

let appState = null;
let currentToken = localStorage.getItem("resq_token");
let currentUser = JSON.parse(localStorage.getItem("resq_user") || "null");
let map = null;
let mapLayers = [];
let pollInterval = null;
let isPolling = false;

document.addEventListener("DOMContentLoaded", () => {
    if (currentToken && currentUser) {
        showDashboard();
    } else {
        showLogin();
    }

    // Refresh immediately when tab becomes visible
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && currentToken) {
            fetchState();
        }
    });
});

function showLogin() {
    document.getElementById("login-view").style.display = "flex";
    document.getElementById("dashboard-view").style.display = "none";
    document.getElementById("user-nav").style.display = "none";
    if (pollInterval) clearInterval(pollInterval);
}

function showDashboard() {
    document.getElementById("login-view").style.display = "none";
    document.getElementById("dashboard-view").style.display = "grid";
    document.getElementById("user-nav").style.display = "flex";

    document.getElementById("user-display-name").textContent = currentUser.display || currentUser.sub;
    const rolePill = document.getElementById("user-role-pill");
    rolePill.textContent = currentUser.role;
    rolePill.className = `role-pill role-${currentUser.role}`;

    // Route views based on role
    document.querySelectorAll(".role-view").forEach(el => el.style.display = "none");
    const roleViewMap = {
        "ADMIN": "admin-view",
        "RESCUE": "rescue-view",
        "AMBULANCE": "ambulance-view",
        "HOSPITAL": "hospital-view"
    };
    const activeViewId = roleViewMap[currentUser.role] || "admin-view";
    document.getElementById(activeViewId).style.display = "block";

    // Role-based visibility for side panel cards
    const riskPanel = document.getElementById("risk-model-panel");
    const logPanel = document.getElementById("adaptation-log-panel");

    if (currentUser.role === "ADMIN") {
        riskPanel.style.display = "block";
        logPanel.style.display = "block";
    } else if (currentUser.role === "HOSPITAL") {
        riskPanel.style.display = "none";
        logPanel.style.display = "block";
    } else {
        riskPanel.style.display = "none";
        logPanel.style.display = "none";
    }

    initMap();
    fetchState();

    if (!pollInterval) {
        pollInterval = setInterval(fetchState, 2500); // 2.5s robust polling loop
    }
}

function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    const errDiv = document.getElementById("login-error");
    errDiv.style.display = "none";

    fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
    })
    .then(res => {
        if (!res.ok) return res.json().then(data => { throw new Error(data.detail || "Login failed"); });
        return res.json();
    })
    .then(data => {
        currentToken = data.token;
        currentUser = data;
        localStorage.setItem("resq_token", data.token);
        localStorage.setItem("resq_user", JSON.stringify(data));
        showDashboard();
    })
    .catch(err => {
        errDiv.textContent = err.message;
        errDiv.style.display = "block";
    });
}

function logout() {
    localStorage.removeItem("resq_token");
    localStorage.removeItem("resq_user");
    currentToken = null;
    currentUser = null;
    showLogin();
}

async function apiRequest(path, options = {}) {
    options.headers = options.headers || {};
    if (currentToken) {
        options.headers["Authorization"] = `Bearer ${currentToken}`;
    }
    const res = await fetch(path, options);
    if (res.status === 401) {
        logout();
        throw new Error("Session expired");
    }
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.detail || "API Request failed");
    }
    return data;
}

async function fetchState() {
    if (isPolling) return;
    isPolling = true;

    const banner = document.getElementById("connection-banner");
    try {
        const state = await apiRequest("/api/state");
        appState = state;
        if (banner) banner.style.display = "none";
        renderState();
    } catch (err) {
        console.warn("State fetch error:", err);
        if (banner) {
            const nowTime = new Date().toLocaleTimeString();
            banner.textContent = `Connection lost, retrying... (Last updated ${nowTime})`;
            banner.style.display = "block";
        }
    } finally {
        isPolling = false;
    }
}

function renderState() {
    if (!appState) return;

    // Render Role View
    if (currentUser.role === "ADMIN") renderAdminView(appState);
    if (currentUser.role === "RESCUE") renderRescueView(appState);
    if (currentUser.role === "AMBULANCE") renderAmbulanceView(appState);
    if (currentUser.role === "HOSPITAL") renderHospitalView(appState);

    // Render Event Log Timeline (if panel visible)
    if (currentUser.role === "ADMIN" || currentUser.role === "HOSPITAL") {
        renderAdaptationLog(appState.events);
    }

    // Render Risk Model Panel (if ADMIN)
    if (currentUser.role === "ADMIN" && appState.risk_model_importances) {
        renderRiskModelPanel(appState.risk_model_importances);
    }

    // Render Leaflet Map
    renderMapState(appState);

    const nowTime = new Date().toLocaleTimeString();
    const updateLabel = document.getElementById("last-updated-time");
    if (updateLabel) updateLabel.textContent = `Updated ${nowTime}`;
}

/* Map Initialization & Layer Updates */
function initMap() {
    if (map) return;

    map = L.map('map').setView([12.9680, 77.5880], 13);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 18
    }).addTo(map);
}

function renderMapState(state) {
    if (!map) return;

    // Invalidate map container size & fit bounds
    map.invalidateSize();
    map.fitBounds([[12.945, 77.565], [12.985, 77.620]], { padding: [20, 20], maxZoom: 15 });

    // Clear previous dynamic layers
    mapLayers.forEach(layer => map.removeLayer(layer));
    mapLayers = [];

    const nodes = state.nodes || {};
    const nodeCoords = {};
    Object.keys(nodes).forEach(nKey => {
        const [lng, lat] = nodes[nKey].coords;
        nodeCoords[nKey] = [lat, lng]; // Leaflet uses [lat, lng]
    });

    // 1. Draw Roads
    (state.roads || []).forEach(road => {
        const srcCoord = nodeCoords[road.src];
        const dstCoord = nodeCoords[road.dst];
        if (!srcCoord || !dstCoord) return;

        let style = { color: "#64748b", weight: 4, opacity: 0.7 };
        if (road.blocked === 1) {
            style = { color: "#000000", weight: 5, opacity: 0.9, dashArray: "6, 8" };
        } else if (road.risk >= 0.4) {
            style = { color: "#f97316", weight: 4, opacity: 0.8 };
        }

        const line = L.polyline([srcCoord, dstCoord], style).addTo(map);
        line.bindPopup(`<b>Road ${road._id}: ${road.name}</b><br>Time: ${road.travel_time} min | Risk: ${road.risk}<br>Status: ${road.blocked ? 'BLOCKED' : 'OPEN'}`);
        mapLayers.push(line);
    });

    // 2. Draw Nodes
    Object.keys(nodes).forEach(nKey => {
        const coord = nodeCoords[nKey];
        const nodeData = nodes[nKey];
        const circle = L.circleMarker(coord, {
            radius: 7,
            fillColor: "#38bdf8",
            color: "#0284c7",
            weight: 2,
            fillOpacity: 0.9
        }).addTo(map);
        circle.bindPopup(`<b>${nodeData.name}</b><br>Elev: ${nodeData.elevation}m | River: ${nodeData.dist_river}km`);
        mapLayers.push(circle);
    });

    // 3. Draw Hospitals
    (state.hospitals || []).forEach(h => {
        const coord = nodeCoords[h.node] || [h.location.coordinates[1], h.location.coordinates[0]];
        const bedsText = `Beds: ${h.available_beds}/${h.total_beds} | ICU: ${h.icu_available}/${h.icu_total}`;
        const color = h.available_beds > 0 ? "#22c55e" : "#ef4444";

        const marker = L.circleMarker(coord, {
            radius: 11,
            fillColor: color,
            color: "#ffffff",
            weight: 2,
            fillOpacity: 0.95
        }).addTo(map);

        marker.bindPopup(`<b>${h.name} (${h._id})</b><br>${bedsText}<br>Trauma-capable: ${h.trauma ? 'Yes' : 'No'}`);
        mapLayers.push(marker);
    });

    // 4. Draw Incidents
    (state.incidents || []).forEach(inc => {
        const coord = nodeCoords[inc.area] || [inc.location.coordinates[1], inc.location.coordinates[0]];
        const marker = L.circleMarker(coord, {
            radius: 10,
            fillColor: "#ef4444",
            color: "#ffffff",
            weight: 2,
            fillOpacity: 0.95
        }).addTo(map);

        marker.bindPopup(`<b>Incident ${inc._id}</b><br>Node: ${inc.area}<br>Priority Score: ${inc.priority_score} (${inc.priority})<br>Victims: ${inc.critical} Critical, ${inc.serious} Serious, ${inc.moderate} Moderate`);
        mapLayers.push(marker);
    });

    // 5. Draw Ambulance Routes (Filtered for AMBULANCE role to ONLY show their route)
    (state.assignments || []).forEach(asgn => {
        if (currentUser.role === "AMBULANCE" && asgn.ambulance_id !== currentUser.ref) {
            return; // Skip other ambulances' routes on ambulance driver view
        }

        // Route to Incident (Blue)
        if (asgn.route_to_incident && asgn.route_to_incident.length > 1) {
            const leafletCoords = asgn.route_to_incident.map(c => [c[1], c[0]]);
            const lineInc = L.polyline(leafletCoords, { color: "#38bdf8", weight: 6, opacity: 0.85 }).addTo(map);
            lineInc.bindPopup(`<b>Ambulance ${asgn.ambulance_id} → Incident ${asgn.incident_id}</b><br>Travel Time: ${asgn.travel_time_to_inc} min`);
            mapLayers.push(lineInc);
        }
        // Route to Hospital (Purple)
        if (asgn.route_to_hospital && asgn.route_to_hospital.length > 1) {
            const leafletCoords = asgn.route_to_hospital.map(c => [c[1], c[0]]);
            const lineHosp = L.polyline(leafletCoords, { color: "#a855f7", weight: 6, opacity: 0.85, dashArray: "4, 6" }).addTo(map);
            lineHosp.bindPopup(`<b>Ambulance ${asgn.ambulance_id} → ${asgn.hospital_name}</b><br>Travel Time: ${asgn.travel_time_to_hosp} min`);
            mapLayers.push(lineHosp);
        }
    });
}

function formatTimestamp(isoStr) {
    if (!isoStr) return "";
    try {
        const d = new Date(isoStr);
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const day = String(d.getDate()).padStart(2, "0");
        const month = months[d.getMonth()];
        const hours = String(d.getHours()).padStart(2, "0");
        const mins = String(d.getMinutes()).padStart(2, "0");
        return `${day} ${month}, ${hours}:${mins}`;
    } catch (e) {
        return isoStr;
    }
}

function renderAdaptationLog(events) {
    const feed = document.getElementById("event-feed");
    if (!feed) return;

    if (!events || events.length === 0) {
        feed.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">No adaptation events logged.</div>';
        return;
    }

    feed.innerHTML = events.map(evt => {
        const timeStr = formatTimestamp(evt.created_at);
        const typeClass = evt.type || "";
        return `
            <div class="event-item ${typeClass}">
                <div class="event-time">[${timeStr}] • ${evt.type ? evt.type.toUpperCase() : 'EVENT'}</div>
                <div class="event-msg">${evt.message}</div>
            </div>
        `;
    }).join("");
}

function renderRiskModelPanel(importances) {
    const container = document.getElementById("feature-importances-container");
    if (!container || !importances) return;

    container.innerHTML = Object.keys(importances).map(feat => {
        const val = importances[feat];
        const pct = Math.round(val * 100);
        return `
            <div class="feature-bar-container">
                <div class="feature-info">
                    <span>${feat}</span>
                    <span>${pct}%</span>
                </div>
                <div class="feature-bar-bg">
                    <div class="feature-bar-fill" style="width: ${pct}%;"></div>
                </div>
            </div>
        `;
    }).join("");
}

function showToast(message) {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.remove();
    }, 5000);
}
